"""The eval-sql entry point, with no database, no network and no gold set file.

The gold set, the database connection and the suite runner are all replaced,
so these tests cover what only the CLI decides: which questions get run, where
the files land, and what the exit code says. Day 20 wires an eval gate to that
exit code, so getting it wrong there is worse than getting a number wrong.
"""

from __future__ import annotations

import datetime as dt
import json

import eval_sql
import pytest

from football_ai.evals.sql import goldset, runner

RUN_ID = "20261116T120000Z-stub-model"


def _goldset() -> goldset.GoldSet:
    return goldset.parse(
        [
            {
                "id": "totals-01",
                "question": "soru 1",
                "category": "totals",
                "reference_sql": "select 1",
                "order_sensitive": True,
            },
            {
                "id": "rates-01",
                "question": "soru 2",
                "category": "rates",
                "reference_sql": "select 1",
                "order_sensitive": True,
            },
            {
                "id": "rates-02",
                "question": "soru 3",
                "category": "rates",
                "reference_sql": "select 1",
                "order_sensitive": True,
            },
        ]
    )


def _question_result(qid: str, correct: bool) -> runner.QuestionResult:
    return runner.QuestionResult(
        id=qid,
        category="totals",
        question=f"soru {qid}",
        model="stub/stub-model",
        generated_sql="select 1 limit 200",
        executes=True,
        correct=correct,
        required_columns=True,
        no_forbidden=True,
        infra_error=False,
        reference_failed=False,
        repairs_used=0,
        structure_differs=False,
        reason="" if correct else "row 1, column 1: expected 1, got 2",
        seconds=1.0,
    )


def _suite(*correctness: bool, model: str = "stub/stub-model") -> runner.SuiteResult:
    return runner.SuiteResult(
        model=model,
        started_at=dt.datetime(2026, 11, 16, 12, 0, 0, tzinfo=dt.UTC),
        results=tuple(
            _question_result(f"q-{i:02d}", ok) for i, ok in enumerate(correctness, start=1)
        ),
        temperature_supported=True,
        reasoning_effort_supported=True,
        retries_used=0,
        seconds=1.0,
    )


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """No gold set file, no database, no provider, no repo writes."""
    monkeypatch.setattr(eval_sql.goldset, "load", lambda path=None: _goldset())
    monkeypatch.setattr(eval_sql, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(eval_sql, "readonly_dsn", lambda: "postgresql://stub/stub")
    monkeypatch.setattr(eval_sql, "LiteLLMClient", lambda **kw: object())
    monkeypatch.setattr(eval_sql, "LATEST_REPORT", tmp_path / "eval_sql_latest.md")


def _stub_run(monkeypatch, suite_factory, seen: list[str] | None = None):
    def fake_run_suite(questions, **kwargs):
        if seen is not None:
            seen.extend(q.id for q in questions)
        return suite_factory(kwargs["model"])

    monkeypatch.setattr(eval_sql, "run_suite", fake_run_suite)


# ---------------------------------------------------------------------------
# Exit codes - day 20 hangs an eval gate on these
# ---------------------------------------------------------------------------


def test_exit_code_is_one_below_threshold(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, False, model=model))
    assert eval_sql.main(["--out", str(tmp_path), "--threshold", "0.70"]) == 1


def test_exit_code_is_zero_at_threshold(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, True, True, False, model=model))
    assert eval_sql.main(["--out", str(tmp_path), "--threshold", "0.70"]) == 0


def test_exit_code_is_one_when_accuracy_cannot_be_computed(tmp_path, monkeypatch):
    """Every question infra-errored: no number, so no pass."""
    _stub_run(monkeypatch, lambda model: _suite(model=model))
    assert eval_sql.main(["--out", str(tmp_path), "--threshold", "0.70"]) == 1


def test_only_the_first_model_gates_the_exit_code(tmp_path, monkeypatch):
    """The weak model is a diagnostic, never a gate."""

    def fake_run_suite(questions, **kwargs):
        if kwargs["model"] == "strong":
            return _suite(True, True, True, True, model="strong")
        return _suite(False, False, False, False, model="weak")

    monkeypatch.setattr(eval_sql, "run_suite", fake_run_suite)
    assert eval_sql.main(["--models", "strong,weak", "--out", str(tmp_path)]) == 0


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------


def test_writes_json_and_markdown_named_by_run_id(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    eval_sql.main(["--model", "stub/stub-model", "--out", str(tmp_path)])
    assert (tmp_path / f"{RUN_ID}.json").exists()
    assert (tmp_path / f"{RUN_ID}.md").exists()


def test_copies_the_markdown_to_the_latest_path(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    eval_sql.main(["--out", str(tmp_path)])
    assert eval_sql.LATEST_REPORT.read_text(encoding="utf-8").startswith("# Text-to-SQL")


def test_json_holds_every_model_in_one_file(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    eval_sql.main(["--models", "strong,weak", "--out", str(tmp_path)])
    written = next(tmp_path.glob("*.json"))
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert [s["model"] for s in payload["suites"]] == ["strong", "weak"]


def test_creates_the_output_directory(tmp_path, monkeypatch):
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    target = tmp_path / "nested" / "dir"
    eval_sql.main(["--model", "stub/stub-model", "--out", str(target)])
    assert (target / f"{RUN_ID}.json").exists()


# ---------------------------------------------------------------------------
# Question selection
# ---------------------------------------------------------------------------


def test_only_filter_restricts_the_questions(tmp_path, monkeypatch):
    seen: list[str] = []
    _stub_run(monkeypatch, lambda model: _suite(True, model=model), seen)
    eval_sql.main(["--only", "totals-01,rates-01", "--out", str(tmp_path)])
    assert seen == ["totals-01", "rates-01"]


def test_category_filter_restricts_the_questions(tmp_path, monkeypatch):
    seen: list[str] = []
    _stub_run(monkeypatch, lambda model: _suite(True, model=model), seen)
    eval_sql.main(["--category", "rates", "--out", str(tmp_path)])
    assert seen == ["rates-01", "rates-02"]


def test_no_filter_runs_everything(tmp_path, monkeypatch):
    seen: list[str] = []
    _stub_run(monkeypatch, lambda model: _suite(True, model=model), seen)
    eval_sql.main(["--out", str(tmp_path)])
    assert seen == ["totals-01", "rates-01", "rates-02"]


def test_unknown_only_id_is_an_error_not_an_empty_run(tmp_path, monkeypatch, capsys):
    """A typo that ran zero questions would be reported as 0% accuracy."""
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    assert eval_sql.main(["--only", "nope-99", "--out", str(tmp_path)]) == 2
    assert "nope-99" in capsys.readouterr().out


def test_unknown_category_is_an_error_not_an_empty_run(tmp_path, monkeypatch, capsys):
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    assert eval_sql.main(["--category", "offside", "--out", str(tmp_path)]) == 2
    assert "offside" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Models and the shared reference cache
# ---------------------------------------------------------------------------


def test_every_model_shares_one_reference_cache(tmp_path, monkeypatch):
    """Otherwise a two-model run executes all 40 reference queries twice."""
    caches: list[object] = []

    def fake_run_suite(questions, **kwargs):
        caches.append(kwargs["reference_cache"])
        return _suite(True, model=kwargs["model"])

    monkeypatch.setattr(eval_sql, "run_suite", fake_run_suite)
    eval_sql.main(["--models", "strong,weak", "--out", str(tmp_path)])
    assert len(caches) == 2
    assert caches[0] is caches[1]
    assert caches[0] is not None


def test_each_model_gets_its_own_client(tmp_path, monkeypatch):
    """The provider flags belong to a model, so the clients cannot be shared."""
    built: list[str] = []
    monkeypatch.setattr(
        eval_sql, "LiteLLMClient", lambda **kw: built.append(kw["model"]) or object()
    )
    _stub_run(monkeypatch, lambda model: _suite(True, model=model))
    eval_sql.main(["--models", "strong,weak", "--out", str(tmp_path)])
    assert built == ["strong", "weak"]


def test_merge_rebuilds_one_report_from_partial_runs(tmp_path, monkeypatch):
    """The free tier allows 20 calls a day, so a 40-question run is split
    across days; --merge turns the batches back into one accuracy number."""
    _stub_run(monkeypatch, lambda model: _suite(True, True, model=model))
    eval_sql.main(["--model", "stub/stub-model", "--only", "totals-01", "--out", str(tmp_path)])

    second = tmp_path / "day2.json"
    second.write_text(
        eval_sql.report.to_json([_suite(False, model="stub/stub-model")]), encoding="utf-8"
    )

    code = eval_sql.main(
        ["--merge", str(tmp_path), "--model", "stub/stub-model", "--out", str(tmp_path)]
    )
    merged = eval_sql.report.from_json(
        max(tmp_path.glob("*-merged.json"), key=lambda p: p.stat().st_mtime).read_text(
            encoding="utf-8"
        )
    )[0]
    assert {r.id for r in merged.results} == {"q-01", "q-02"}
    assert code in (0, 1)


def test_merge_without_files_is_an_error(tmp_path):
    assert eval_sql.main(["--merge", str(tmp_path / "empty"), "--out", str(tmp_path)]) == 2


def test_merge_makes_no_provider_call(tmp_path, monkeypatch):
    """Merging is offline: it must not spend a request from the daily quota."""

    def explode(*_a, **_k):
        raise AssertionError("merge called the provider")

    monkeypatch.setattr(eval_sql, "run_suite", explode)
    monkeypatch.setattr(eval_sql, "LiteLLMClient", explode)
    source = tmp_path / "run.json"
    source.write_text(
        eval_sql.report.to_json([_suite(True, model="stub/stub-model")]), encoding="utf-8"
    )
    assert eval_sql.main(["--merge", str(tmp_path), "--out", str(tmp_path)]) == 0


def test_progress_is_printed_per_question(tmp_path, monkeypatch, capsys):
    """A 40-question run takes minutes; silence is indistinguishable from a hang."""

    def fake_run_suite(questions, **kwargs):
        suite = _suite(True, False, model=kwargs["model"])
        for result in suite.results:
            kwargs["on_result"](result)
        return suite

    monkeypatch.setattr(eval_sql, "run_suite", fake_run_suite)
    eval_sql.main(["--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "q-01" in out
    assert "q-02" in out


def test_smoke_runs_one_question_per_category(tmp_path, monkeypatch):
    """A quick regression check that fits inside one day of free-tier quota:
    20 requests a day means the full 40-question suite cannot be a habit."""
    seen: list[str] = []
    _stub_run(monkeypatch, lambda model: _suite(True, model=model), seen)
    eval_sql.main(["--smoke", "--out", str(tmp_path)])
    assert seen == ["totals-01", "rates-01"]


def test_smoke_and_category_cannot_be_combined(tmp_path, capsys):
    assert eval_sql.main(["--smoke", "--category", "rates", "--out", str(tmp_path)]) == 2
    assert "smoke" in capsys.readouterr().out
