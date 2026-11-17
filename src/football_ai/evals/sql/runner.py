"""Run the benchmark and score each question on four dimensions.

A single accuracy number hides four different failures that need four
different fixes, so each gets its own field:

* `executes` - did the query survive the guard and the database? An invented
  column lands here.
* `correct` - do the rows match the reference? This is the headline number.
* `required_columns` - is the output usable? A percentile with no comparison
  group size is a number nobody can interpret. Right answer, unusable shape.
* `no_forbidden` - was the number reached the right way? A 900-minute filter
  on a question about season totals can return identical rows and still be
  wrong reasoning.

Two outcomes are deliberately NOT charged to the model, and both set
`correct=None` so they leave the denominator rather than counting as errors:

* `infra_error` - the provider never answered (503, rate limit, timeout past
  the retries). Counting these as wrong answers would make the score track
  the provider's weather.
* `reference_failed` - the gold set's own SQL did not run, which happens when
  a migration renames a column. Charging that to the model would send the
  reader looking for a prompt bug that is not there.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import psycopg

from football_ai.evals.sql import compare, execute, structure
from football_ai.evals.sql.goldset import Question
from football_ai.sql_agent import generate, guard

# How many rows of each side to keep for a question that is not fully green.
# Enough to see which answer is defensible; few enough that the report stays
# readable when a third of the suite fails.
ROWS_KEPT = 5


@dataclass(frozen=True)
class QuestionResult:
    id: str
    category: str
    question: str
    model: str
    generated_sql: str | None
    executes: bool
    correct: bool | None
    required_columns: bool
    no_forbidden: bool
    infra_error: bool
    reference_failed: bool
    repairs_used: int
    structure_differs: bool
    reason: str
    seconds: float
    reference_rows: tuple[tuple, ...] = ()
    candidate_rows: tuple[tuple, ...] = ()

    @property
    def green(self) -> bool:
        """Fully clean: ran, right, usable, and reached the right way."""
        return (
            self.executes
            and self.correct is not False
            and self.required_columns
            and self.no_forbidden
            and not self.infra_error
            and not self.reference_failed
        )


@dataclass(frozen=True)
class SuiteResult:
    model: str
    started_at: dt.datetime
    results: tuple[QuestionResult, ...]
    temperature_supported: bool
    reasoning_effort_supported: bool
    retries_used: int
    seconds: float = 0.0
    # Billed tokens as the provider reported them, so a run can price itself.
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def model_slug(self) -> str:
        """`gemini/gemini-3.8-flash` -> `gemini-3.8-flash`, filename-safe."""
        return self.model.rsplit("/", 1)[-1].replace(":", "-")

    @property
    def run_id(self) -> str:
        stamp = self.started_at.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{self.model_slug}"


@dataclass
class _Verdict:
    """Mutable scratch space while a question is being scored."""

    executes: bool = False
    correct: bool | None = None
    infra_error: bool = False
    reference_failed: bool = False
    reasons: list[str] = field(default_factory=list)

    def note(self, reason: str) -> None:
        if reason:
            self.reasons.append(reason)


def _reference_execution(
    question: Question,
    conn: psycopg.Connection,
    max_rows: int,
    cache: dict[str, execute.Execution] | None,
) -> execute.Execution:
    """The reference result, from the cache when one was supplied.

    Caching is safe because the season is frozen data, and it halves the
    database work on a two-model run.
    """
    if cache is not None and question.id in cache:
        return cache[question.id]
    assert question.reference_sql is not None
    result = execute.run_sql(conn, question.reference_sql, max_rows=max_rows)
    if cache is not None:
        cache[question.id] = result
    return result


def run_question(
    question: Question,
    *,
    conn: psycopg.Connection,
    client: generate.LLMClient,
    model: str = "",
    max_rows: int = guard.DEFAULT_LIMIT,
    reference_cache: dict[str, execute.Execution] | None = None,
) -> QuestionResult:
    """Generate SQL for one question and score it."""
    started = dt.datetime.now(dt.UTC)
    verdict = _Verdict()
    generated: str | None = None
    repairs = 0
    reference_rows: tuple[tuple, ...] = ()
    candidate_rows: tuple[tuple, ...] = ()
    structure_differs = False

    try:
        produced = generate.text_to_sql(
            question.question, conn=conn, client=client, max_rows=max_rows
        )
    except Exception as exc:
        # Defensive: text_to_sql catches provider errors itself (see below),
        # so reaching here means a client raised outside the call it guards.
        verdict.infra_error = True
        verdict.note(f"provider failure: {type(exc).__name__}: {exc}")
        return _result(question, model, None, verdict, repairs, structure_differs, started, (), ())

    repairs = produced.repairs_used
    generated = produced.sql

    # Telling "the provider never answered" from "the model answered badly",
    # structurally rather than by matching the error text: every reply that
    # arrives appends an Attempt, including one the guard then refuses. So an
    # empty attempts list means no reply ever arrived - a 503, a rate limit, a
    # timeout past the retries, or a retired model name. Not a wrong answer,
    # and excluded from the denominator.
    if not produced.ok and not produced.attempts:
        verdict.infra_error = True
        verdict.note(produced.error or "the provider returned nothing")
        return _result(question, model, None, verdict, repairs, structure_differs, started, (), ())

    # Structural dimensions are scored on whatever the model produced, even
    # when it never ran, so the report can still say what was wrong with it.
    missing = structure.missing_required(generated or "", question.required_columns)
    violated = structure.violated_forbidden(generated or "", question.forbidden)
    if missing:
        verdict.note(f"missing required column(s): {', '.join(missing)}")
    if violated:
        verdict.note(f"forbidden structure(s): {', '.join(violated)}")

    if not produced.ok or generated is None:
        verdict.note(produced.error or "no SQL was produced")
        if question.scores_correctness:
            verdict.correct = False
        return _result(
            question, model, generated, verdict, repairs, structure_differs, started, (), ()
        )

    candidate = execute.run_sql(conn, generated, max_rows=max_rows)
    verdict.executes = candidate.ok
    if not candidate.ok:
        verdict.note(candidate.error or candidate.guard_refusal or "the query did not run")
        if question.scores_correctness:
            verdict.correct = False

    if question.scores_correctness:
        reference = _reference_execution(question, conn, max_rows, reference_cache)
        if not reference.ok:
            # The gold set is broken, not the model. Leaves the denominator.
            verdict.reference_failed = True
            verdict.correct = None
            verdict.reasons = [
                "the reference query in the gold set did not run: "
                f"{reference.error or reference.guard_refusal}"
            ]
            return _result(
                question, model, generated, verdict, repairs, structure_differs, started, (), ()
            )

        if candidate.ok:
            structure_differs = structure.relations_used(generated) != structure.relations_used(
                question.reference_sql or ""
            )
            outcome = compare.compare(
                reference.rows,
                candidate.rows,
                order_sensitive=question.order_sensitive,
            )
            verdict.correct = outcome.equal
            if not outcome.equal:
                verdict.note(outcome.reason)

        if verdict.correct is not True or missing or violated:
            reference_rows = tuple(reference.rows[:ROWS_KEPT])
            candidate_rows = tuple(candidate.rows[:ROWS_KEPT])
    elif missing or violated or not candidate.ok:
        candidate_rows = tuple(candidate.rows[:ROWS_KEPT])

    return _result(
        question,
        model,
        generated,
        verdict,
        repairs,
        structure_differs,
        started,
        reference_rows,
        candidate_rows,
    )


def _result(
    question: Question,
    model: str,
    generated: str | None,
    verdict: _Verdict,
    repairs: int,
    structure_differs: bool,
    started: dt.datetime,
    reference_rows: tuple[tuple, ...],
    candidate_rows: tuple[tuple, ...],
) -> QuestionResult:
    missing = structure.missing_required(generated or "", question.required_columns)
    violated = structure.violated_forbidden(generated or "", question.forbidden)
    return QuestionResult(
        id=question.id,
        category=question.category,
        question=question.question,
        model=model,
        generated_sql=generated,
        executes=verdict.executes,
        correct=verdict.correct,
        required_columns=not missing,
        no_forbidden=not violated,
        infra_error=verdict.infra_error,
        reference_failed=verdict.reference_failed,
        repairs_used=repairs,
        structure_differs=structure_differs,
        reason="; ".join(verdict.reasons),
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        reference_rows=reference_rows,
        candidate_rows=candidate_rows,
    )


def run_suite(
    questions: Sequence[Question],
    *,
    conn: psycopg.Connection,
    client: generate.LLMClient,
    model: str,
    on_result: Callable[[QuestionResult], None] | None = None,
    max_rows: int = guard.DEFAULT_LIMIT,
    reference_cache: dict[str, execute.Execution] | None = None,
) -> SuiteResult:
    """Score every question against one model."""
    started = dt.datetime.now(dt.UTC)
    results: list[QuestionResult] = []
    for question in questions:
        result = run_question(
            question,
            conn=conn,
            client=client,
            model=model,
            max_rows=max_rows,
            reference_cache=reference_cache,
        )
        results.append(result)
        if on_result is not None:
            on_result(result)

    # Read with getattr: a stub client in the tests has no provider flags, and
    # requiring them would make the test double carry production details.
    return SuiteResult(
        model=model,
        started_at=started,
        results=tuple(results),
        temperature_supported=bool(getattr(client, "temperature_supported", True)),
        reasoning_effort_supported=bool(getattr(client, "reasoning_effort_supported", True)),
        retries_used=int(getattr(client, "retries_used", 0)),
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        prompt_tokens=int(getattr(client, "prompt_tokens", 0)),
        completion_tokens=int(getattr(client, "completion_tokens", 0)),
    )
