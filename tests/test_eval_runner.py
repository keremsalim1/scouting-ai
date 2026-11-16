"""Four-dimension scoring, with no database and no network.

The runner is where "the model was wrong" has to be told apart from three
other things that look identical in a bare accuracy number: the provider was
down, the gold set's own query is broken, and the answer was right but the
output is unusable. Each of those gets its own field, and these tests pin
which one fires.
"""

from __future__ import annotations

import datetime as dt

import pytest

from football_ai.evals.sql import goldset, runner
from football_ai.sql_agent import generate

REFERENCE = "select player, goals from football.player_season where comp = 'eng' limit 5"
ROWS = [("Saka", 11), ("Haaland", 20)]


class StubClient:
    """Returns canned replies in order, like tests/test_sql_generate.py."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    def complete(self, system: str, user: str) -> str:
        if not self.replies:
            raise AssertionError("StubClient ran out of replies")
        return self.replies.pop(0)


class ExplodingClient:
    def __init__(self, message: str = "503 Service Unavailable") -> None:
        self.message = message

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError(self.message)


def _question(**over: object) -> goldset.Question:
    base = {
        "id": "totals-01",
        "question": "Premier League'de en cok gol atan oyuncular",
        "category": "totals",
        "reference_sql": REFERENCE,
        "order_sensitive": True,
    }
    return goldset.parse([{**base, **over}]).questions[0]


@pytest.fixture(autouse=True)
def _no_schema_lookup(monkeypatch):
    """text_to_sql asks the database to describe itself; pin it instead."""
    monkeypatch.setattr(generate, "schema_text", lambda conn, refresh=False: "SCHEMA HERE\n")


@pytest.fixture
def executor(monkeypatch):
    """Route execute.run_sql to canned results keyed by a substring of the SQL.

    Keyed on substrings rather than exact text because the guard rewrites both
    sides before they reach the executor.
    """

    class Executor:
        def __init__(self) -> None:
            self.default = runner.execute.Execution(
                ok=True, columns=("player", "goals"), rows=list(ROWS), sql="x"
            )
            self.by_marker: list[tuple[str, runner.execute.Execution]] = []
            self.calls: list[str] = []

        def when(self, marker: str, execution: runner.execute.Execution) -> None:
            self.by_marker.append((marker, execution))

        def __call__(self, conn, sql, *, max_rows=200):
            self.calls.append(sql)
            for marker, execution in self.by_marker:
                if marker.lower() in sql.lower():
                    return execution
            return self.default

        def count(self, marker: str) -> int:
            return sum(1 for sql in self.calls if marker.lower() in sql.lower())

    stub = Executor()
    monkeypatch.setattr(runner.execute, "run_sql", stub)
    return stub


def _ok(rows, columns=("player", "goals")):
    return runner.execute.Execution(ok=True, columns=columns, rows=list(rows), sql="x")


# ---------------------------------------------------------------------------
# The happy path and the "right answer, different query" case
# ---------------------------------------------------------------------------


def test_different_sql_same_rows_scores_correct(executor):
    client = StubClient(
        "select player, goals from football.player_season where comp = 'eng' order by goals limit 5"
    )
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.correct is True
    assert result.executes is True
    assert result.required_columns is True
    assert result.no_forbidden is True
    assert result.structure_differs is False
    assert result.reason == ""


def test_structure_differs_is_reported_but_does_not_fail(executor):
    client = StubClient("select player, goals from football.player_season_club limit 5")
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.correct is True
    assert result.structure_differs is True


def test_green_questions_keep_no_rows(executor):
    client = StubClient(REFERENCE)
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.correct is True
    assert result.reference_rows == ()
    assert result.candidate_rows == ()


# ---------------------------------------------------------------------------
# The model produced nothing usable
# ---------------------------------------------------------------------------


def test_prose_answer_scores_incorrect_without_raising(executor):
    client = StubClient("I cannot answer that.", "Still cannot.")
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.executes is False
    assert result.correct is False
    assert result.infra_error is False
    assert result.reason


def test_empty_answer_scores_incorrect_without_raising(executor):
    client = StubClient("", "")
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.executes is False
    assert result.correct is False
    assert "empty" in result.reason.lower()


def test_an_invented_column_scores_incorrect(executor):
    executor.when("pressures", runner.execute.Execution(ok=False, error="column does not exist"))
    client = StubClient("select player, pressures from football.player_season limit 5")
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.executes is False
    assert result.correct is False
    assert "does not exist" in result.reason


# ---------------------------------------------------------------------------
# Not the model's fault
# ---------------------------------------------------------------------------


def test_provider_failure_is_infra_error_not_a_wrong_answer(executor):
    result = runner.run_question(_question(), conn=None, client=ExplodingClient())
    assert result.infra_error is True
    assert result.correct is None
    assert "503" in result.reason


def test_a_refused_answer_is_not_an_infra_error(executor):
    """The signal is an empty attempts list. A guard refusal appends an
    attempt, so it must stay a wrong answer rather than leaving the
    denominator as provider weather."""
    client = StubClient("delete from football.players", "drop table football.players")
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.infra_error is False
    assert result.correct is False


def test_a_retired_model_name_is_an_infra_error(executor):
    result = runner.run_question(
        _question(),
        conn=None,
        client=ExplodingClient("404 model not found"),
    )
    assert result.infra_error is True
    assert result.correct is None


def test_a_broken_reference_sql_is_reported_as_such_not_as_a_model_failure(executor):
    executor.when("order by goals", _ok(ROWS))
    executor.when(
        "player_season",
        runner.execute.Execution(ok=False, error='column "goals" does not exist'),
    )
    client = StubClient(
        "select player, goals from football.player_season where comp = 'eng' order by goals limit 5"
    )
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.reference_failed is True
    assert result.correct is None
    assert "reference" in result.reason.lower()


# ---------------------------------------------------------------------------
# Right number, wrong shape or wrong route
# ---------------------------------------------------------------------------


def test_forbidden_minutes_filter_fails_that_dimension_only(executor):
    question = _question(forbidden=["minutes_filter"])
    client = StubClient(
        "select player, goals from football.player_season "
        "where comp = 'eng' and minutes_played >= 900 limit 5"
    )
    result = runner.run_question(question, conn=None, client=client)
    assert result.correct is True
    assert result.no_forbidden is False
    assert "minutes_filter" in result.reason


def test_missing_required_column_fails_that_dimension_only(executor):
    question = _question(required_columns=["player", "teams"])
    client = StubClient(REFERENCE)
    result = runner.run_question(question, conn=None, client=client)
    assert result.correct is True
    assert result.required_columns is False
    assert "teams" in result.reason


def test_structural_dimensions_are_scored_even_when_execution_failed(executor):
    """The report must still say what was wrong with a query that did not run."""
    executor.when("player_season", runner.execute.Execution(ok=False, error="boom"))
    question = _question(required_columns=["teams"])
    client = StubClient("select player, goals from football.player_season limit 5")
    result = runner.run_question(question, conn=None, client=client)
    assert result.executes is False
    assert result.required_columns is False


# ---------------------------------------------------------------------------
# unanswerable
# ---------------------------------------------------------------------------


def test_unanswerable_question_scores_none_for_correct(executor):
    question = _question(id="unans-01", category="unanswerable", reference_sql=None)
    client = StubClient("select player from football.player_season limit 5")
    result = runner.run_question(question, conn=None, client=client)
    assert result.correct is None
    assert result.executes is True
    assert result.reference_failed is False


def test_unanswerable_question_runs_no_reference_query(executor):
    question = _question(id="unans-01", category="unanswerable", reference_sql=None)
    client = StubClient("select player from football.player_season limit 5")
    runner.run_question(question, conn=None, client=client)
    assert len(executor.calls) == 1


# ---------------------------------------------------------------------------
# Repairs, rows kept, caching
# ---------------------------------------------------------------------------


def test_repairs_used_is_carried_through(executor):
    client = StubClient("delete from football.players", REFERENCE)
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.repairs_used == 1
    assert result.correct is True


def test_failed_questions_keep_the_first_rows_of_both_sides(executor):
    reference_rows = [(f"ref{i}", i) for i in range(6)]
    candidate_rows = [(f"cand{i}", i) for i in range(6)]
    executor.when("order by goals", _ok(candidate_rows))
    executor.when("player_season", _ok(reference_rows))
    client = StubClient(
        "select player, goals from football.player_season where comp = 'eng' order by goals limit 9"
    )
    result = runner.run_question(_question(), conn=None, client=client)
    assert result.correct is False
    assert len(result.reference_rows) == runner.ROWS_KEPT
    assert len(result.candidate_rows) == runner.ROWS_KEPT


def test_reference_cache_executes_each_reference_once(executor):
    cache: dict = {}
    question = _question()
    for _ in range(2):
        runner.run_question(
            question,
            conn=None,
            client=StubClient(REFERENCE),
            reference_cache=cache,
        )
    assert executor.count("comp = 'eng'") == 3  # 2 candidates + 1 reference
    assert set(cache) == {question.id}


def test_without_a_cache_the_reference_runs_every_time(executor):
    question = _question()
    for _ in range(2):
        runner.run_question(question, conn=None, client=StubClient(REFERENCE))
    assert executor.count("comp = 'eng'") == 4


# ---------------------------------------------------------------------------
# Whole suite
# ---------------------------------------------------------------------------


class _FlaggedClient(StubClient):
    temperature_supported = False
    reasoning_effort_supported = True
    retries_used = 7


def test_run_suite_calls_on_result_per_question_and_carries_flags(executor):
    questions = goldset.parse(
        [
            {
                "id": f"totals-0{i}",
                "question": "soru",
                "category": "totals",
                "reference_sql": REFERENCE,
                "order_sensitive": True,
            }
            for i in (1, 2, 3)
        ]
    ).questions
    client = _FlaggedClient(*([REFERENCE] * 3))
    seen: list[str] = []
    suite = runner.run_suite(
        questions,
        conn=None,
        client=client,
        model="gemini/gemini-3.8-flash",
        on_result=lambda r: seen.append(r.id),
    )
    assert seen == ["totals-01", "totals-02", "totals-03"]
    assert suite.temperature_supported is False
    assert suite.reasoning_effort_supported is True
    assert suite.retries_used == 7
    assert all(r.model == "gemini/gemini-3.8-flash" for r in suite.results)


def test_run_suite_tolerates_a_client_without_provider_flags(executor):
    suite = runner.run_suite(
        (_question(),), conn=None, client=StubClient(REFERENCE), model="stub/model"
    )
    assert suite.temperature_supported is True
    assert suite.retries_used == 0


def test_run_id_is_stable_and_model_slugged():
    suite = runner.SuiteResult(
        model="gemini/gemini-3.8-flash",
        started_at=dt.datetime(2026, 11, 16, 12, 0, 0, tzinfo=dt.UTC),
        results=(),
        temperature_supported=True,
        reasoning_effort_supported=True,
        retries_used=0,
    )
    assert suite.run_id == "20261116T120000Z-gemini-3.8-flash"
