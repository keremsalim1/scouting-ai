"""Scoring and rendering, built from synthetic QuestionResults.

The arithmetic here decides what the headline number means, so the
denominator rules get the most tests: `unanswerable` questions, provider
failures and broken reference queries all leave the denominator, and the
report has to say so rather than quietly shrinking it.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from football_ai.evals.sql import report, runner


def _result(
    qid: str = "totals-01",
    *,
    category: str = "totals",
    correct: bool | None = True,
    executes: bool = True,
    required_columns: bool = True,
    no_forbidden: bool = True,
    infra_error: bool = False,
    reference_failed: bool = False,
    repairs_used: int = 0,
    generated_sql: str | None = "select 1 limit 200",
    reason: str = "",
    reference_rows: tuple[tuple, ...] = (),
    candidate_rows: tuple[tuple, ...] = (),
    structure_differs: bool = False,
) -> runner.QuestionResult:
    return runner.QuestionResult(
        id=qid,
        category=category,
        question=f"soru {qid}",
        model="gemini/gemini-3.8-flash",
        generated_sql=generated_sql,
        executes=executes,
        correct=correct,
        required_columns=required_columns,
        no_forbidden=no_forbidden,
        infra_error=infra_error,
        reference_failed=reference_failed,
        repairs_used=repairs_used,
        structure_differs=structure_differs,
        reason=reason,
        seconds=1.0,
        reference_rows=reference_rows,
        candidate_rows=candidate_rows,
    )


def _suite(
    *results: runner.QuestionResult,
    model: str = "gemini/gemini-3.8-flash",
    temperature_supported: bool = True,
    reasoning_effort_supported: bool = True,
    retries_used: int = 0,
) -> runner.SuiteResult:
    return runner.SuiteResult(
        model=model,
        started_at=dt.datetime(2026, 11, 16, 12, 0, 0, tzinfo=dt.UTC),
        results=results,
        temperature_supported=temperature_supported,
        reasoning_effort_supported=reasoning_effort_supported,
        retries_used=retries_used,
        seconds=12.5,
    )


# ---------------------------------------------------------------------------
# The denominator
# ---------------------------------------------------------------------------


def test_unanswerable_is_excluded_from_the_denominator():
    results = [
        _result("totals-01", correct=True),
        _result("totals-02", correct=True),
        _result("totals-03", correct=True),
        _result("totals-04", correct=False),
        _result("unans-01", category="unanswerable", correct=None),
        _result("unans-02", category="unanswerable", correct=None),
    ]
    scores = report.score(results)
    assert scores.scored == 4
    assert scores.accuracy == pytest.approx(0.75)


def test_infra_errors_are_excluded_from_the_denominator():
    results = [
        _result("totals-01", correct=True),
        _result("totals-02", correct=True),
        _result("totals-03", correct=False),
        _result("totals-04", correct=None, infra_error=True, executes=False),
    ]
    scores = report.score(results)
    assert scores.scored == 3
    assert scores.infra_errors == 1
    assert scores.accuracy == pytest.approx(2 / 3)


def test_reference_failures_are_counted_and_excluded():
    results = [
        _result("totals-01", correct=True),
        _result("totals-02", correct=True),
        _result("totals-03", correct=False),
        _result("totals-04", correct=None, reference_failed=True),
    ]
    scores = report.score(results)
    assert scores.reference_failures == 1
    assert scores.scored == 3


def test_accuracy_is_none_when_everything_infra_errored():
    results = [
        _result("totals-01", correct=None, infra_error=True, executes=False),
        _result("totals-02", correct=None, infra_error=True, executes=False),
    ]
    scores = report.score(results)
    assert scores.scored == 0
    assert scores.accuracy is None


def test_accuracy_is_none_for_an_empty_result_list():
    assert report.score([]).accuracy is None


def test_the_other_three_dimensions_are_counted():
    results = [
        _result("totals-01", required_columns=False),
        _result("totals-02", no_forbidden=False),
        _result("totals-03", executes=False, correct=False),
    ]
    scores = report.score(results)
    assert scores.executes == 2
    assert scores.required_columns == 2
    assert scores.no_forbidden == 2


def test_by_category_scores_each_category_separately():
    suite = _suite(
        _result("totals-01", correct=True),
        _result("totals-02", correct=True),
        _result("rates-01", category="rates", correct=True),
        _result("rates-02", category="rates", correct=False),
    )
    cats = report.by_category(suite)
    assert cats["totals"].accuracy == pytest.approx(1.0)
    assert cats["rates"].accuracy == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def test_markdown_does_not_crash_when_accuracy_is_none():
    suite = _suite(_result("totals-01", correct=None, infra_error=True, executes=False))
    assert "n/a" in report.to_markdown([suite], threshold=0.70)


def test_markdown_states_the_denominator():
    results = [_result(f"totals-{i:02d}") for i in range(36)]
    results += [_result(f"unans-{i:02d}", category="unanswerable", correct=None) for i in range(4)]
    assert "36" in report.to_markdown([_suite(*results)], threshold=0.70)


def test_markdown_warns_above_the_infra_error_ratio():
    results = [_result(f"totals-{i:02d}") for i in range(8)]
    results += [
        _result(f"totals-1{i}", correct=None, infra_error=True, executes=False) for i in range(2)
    ]
    assert "karşılaştırılabilir değil" in report.to_markdown([_suite(*results)], threshold=0.70)


def test_markdown_does_not_warn_below_the_infra_error_ratio():
    results = [_result(f"totals-{i:02d}") for i in range(20)]
    results += [_result("totals-21", correct=None, infra_error=True, executes=False)]
    assert "karşılaştırılabilir değil" not in report.to_markdown([_suite(*results)], threshold=0.70)


def test_markdown_reports_repair_counts_in_three_buckets():
    suite = _suite(
        _result("totals-01", repairs_used=0),
        _result("totals-02", repairs_used=1),
        _result("totals-03", repairs_used=1, correct=False, executes=False),
    )
    md = report.to_markdown([suite], threshold=0.70)
    # Matched on substrings that avoid the first letter: Python's str.lower()
    # maps "İ" (U+0130) to "i" + U+0307, not to "i", so a lowercased compare
    # against Turkish headings silently never matches.
    assert "denemede geçen: 1" in md
    assert "Onarımla düzelen: 1" in md
    assert "reddedilen: 1" in md


def test_markdown_flags_dropped_parameters():
    suite = _suite(_result(), temperature_supported=False)
    assert "temperature" in report.to_markdown([suite], threshold=0.70)


def test_markdown_does_not_mention_parameters_that_were_accepted():
    suite = _suite(_result())
    assert "temperature" not in report.to_markdown([suite], threshold=0.70)


def test_markdown_names_broken_references_separately_from_model_errors():
    suite = _suite(
        _result("totals-01", correct=None, reference_failed=True, reason="reference did not run")
    )
    assert "gold set" in report.to_markdown([suite], threshold=0.70).lower()


def test_markdown_prints_both_row_sets_for_a_failed_question():
    suite = _suite(
        _result(
            "totals-01",
            correct=False,
            reason="row 1, column 2: expected 11, got 9",
            reference_rows=(("Saka", 11),),
            candidate_rows=(("Saka", 9),),
        )
    )
    md = report.to_markdown([suite], threshold=0.70).lower()
    assert "beklenen" in md
    assert "gelen" in md


def test_markdown_breaks_the_excluded_questions_down_by_cause():
    """Three different things leave the denominator and they need three
    different fixes, so the report must count each rather than print a total."""
    suite = _suite(
        _result("totals-01", correct=True),
        _result("unans-01", category="unanswerable", correct=None),
        _result("unans-02", category="unanswerable", correct=None),
        _result("totals-02", correct=None, infra_error=True, executes=False),
        _result("totals-03", correct=None, reference_failed=True),
    )
    md = report.to_markdown([suite], threshold=0.70)
    assert "cevaplanamaz 2" in md
    assert "altyapı hatası 1" in md
    assert "bozuk referans 1" in md


def test_markdown_says_whether_the_threshold_was_met():
    passing = _suite(*[_result(f"totals-{i:02d}") for i in range(10)])
    failing = _suite(*[_result(f"totals-{i:02d}", correct=False) for i in range(10)])
    assert "eşik" in report.to_markdown([passing], threshold=0.70).lower()
    assert "eşik" in report.to_markdown([failing], threshold=0.70).lower()


def test_markdown_lists_every_category_present():
    suite = _suite(
        _result("totals-01"),
        _result("rates-01", category="rates"),
        _result("unans-01", category="unanswerable", correct=None),
    )
    md = report.to_markdown([suite], threshold=0.70)
    for name in ("totals", "rates", "unanswerable"):
        assert name in md


def test_markdown_omits_the_appendix_when_every_question_is_green():
    suite = _suite(_result("totals-01"), _result("totals-02"))
    assert "Soru soru" not in report.to_markdown([suite], threshold=0.70)


# ---------------------------------------------------------------------------
# Two models
# ---------------------------------------------------------------------------


def test_disagreements_lists_questions_where_verdicts_differ():
    strong = _suite(
        _result("rates-01", category="rates", correct=True),
        _result("rates-02", category="rates", correct=True),
    )
    weak = _suite(
        _result("rates-01", category="rates", correct=True),
        _result("rates-02", category="rates", correct=False),
        model="gemini/gemini-3.1-flash-lite",
    )
    found = report.disagreements(strong, weak)
    assert [x.id for x in found] == ["rates-02"]
    assert found[0].verdicts["gemini/gemini-3.8-flash"] is True
    assert found[0].verdicts["gemini/gemini-3.1-flash-lite"] is False


def test_disagreements_ignores_questions_missing_from_one_suite():
    full = _suite(
        _result("rates-01", category="rates", correct=True),
        _result("rates-02", category="rates", correct=True),
    )
    partial = _suite(
        _result("rates-02", category="rates", correct=False),
        model="gemini/gemini-3.1-flash-lite",
    )
    assert [x.id for x in report.disagreements(full, partial)] == ["rates-02"]


def test_disagreement_carries_each_models_sql_under_an_honest_name():
    """The field holds SQL, so it must not be called `relations`: a consumer
    reading that name would expect relation names and get a query."""
    strong = _suite(_result("rates-01", category="rates", correct=True))
    weak = _suite(
        _result("rates-01", category="rates", correct=False),
        model="gemini/gemini-3.1-flash-lite",
    )
    found = report.disagreements(strong, weak)[0]
    assert found.generated_sql["gemini/gemini-3.8-flash"] == "select 1 limit 200"
    assert not hasattr(found, "relations")


def test_disagreements_is_empty_when_both_models_agree():
    a = _suite(_result("rates-01", category="rates", correct=True))
    b = _suite(_result("rates-01", category="rates", correct=True), model="other/model")
    assert report.disagreements(a, b) == ()


def test_markdown_includes_a_disagreement_table_for_two_suites():
    strong = _suite(_result("rates-01", category="rates", correct=True))
    weak = _suite(
        _result("rates-01", category="rates", correct=False),
        model="gemini/gemini-3.1-flash-lite",
    )
    md = report.to_markdown([strong, weak], threshold=0.70)
    assert "uyuşmazlık" in md.lower()
    assert "rates-01" in md


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_round_trips_the_generated_sql():
    payload = json.loads(report.to_json([_suite(_result())]))
    assert payload["suites"][0]["results"][0]["generated_sql"] == "select 1 limit 200"


def test_json_carries_the_run_id_and_the_scores():
    payload = json.loads(report.to_json([_suite(_result())]))
    suite = payload["suites"][0]
    assert suite["run_id"] == "20261116T120000Z-gemini-3.8-flash"
    assert suite["scores"]["scored"] == 1


def test_json_serialises_kept_rows():
    suite = _suite(
        _result(
            "totals-01",
            correct=False,
            reference_rows=(("Saka", 11),),
            candidate_rows=(("Saka", 9),),
        )
    )
    payload = json.loads(report.to_json([suite]))
    assert payload["suites"][0]["results"][0]["reference_rows"] == [["Saka", 11]]


def test_from_json_round_trips_a_suite():
    suite = _suite(_result("totals-01", correct=True), _result("rates-01", correct=False))
    restored = report.from_json(report.to_json([suite]))[0]
    assert restored.model == suite.model
    assert restored.run_id == suite.run_id
    assert [r.id for r in restored.results] == ["totals-01", "rates-01"]
    assert [r.correct for r in restored.results] == [True, False]


def test_from_json_restores_the_rows_kept_for_a_failure():
    suite = _suite(
        _result(
            "totals-01",
            correct=False,
            reference_rows=(("Saka", 11),),
            candidate_rows=(("Saka", 9),),
        )
    )
    restored = report.from_json(report.to_json([suite]))[0]
    assert restored.results[0].reference_rows == (("Saka", 11),)


def test_merge_combines_partial_runs_of_one_model():
    """The free tier allows 20 calls a day, so a 40-question run has to be
    split across days and stitched back into one accuracy number."""
    day1 = _suite(_result("totals-01", correct=True), _result("totals-02", correct=True))
    day2 = _suite(_result("rates-01", correct=False))
    merged = report.merge([day1, day2])
    assert [r.id for r in merged.results] == ["totals-01", "totals-02", "rates-01"]
    assert report.score(merged.results).scored == 3
    assert report.score(merged.results).correct == 2


def test_merge_lets_a_later_run_replace_an_earlier_answer():
    """Re-running one question after a fix must not leave both verdicts in."""
    first = _suite(_result("totals-01", correct=False))
    second = _suite(_result("totals-01", correct=True))
    merged = report.merge([first, second])
    assert len(merged.results) == 1
    assert merged.results[0].correct is True


def test_merge_keeps_the_earliest_start_and_sums_the_time():
    day1 = _suite(_result("totals-01"))
    day2 = runner.SuiteResult(
        model="gemini/gemini-3.8-flash",
        started_at=dt.datetime(2026, 11, 18, 9, 0, 0, tzinfo=dt.UTC),
        results=(_result("rates-01"),),
        temperature_supported=True,
        reasoning_effort_supported=True,
        retries_used=3,
        seconds=20.0,
    )
    merged = report.merge([day1, day2])
    assert merged.started_at == day1.started_at
    assert merged.seconds == pytest.approx(32.5)
    assert merged.retries_used == 3


def test_merge_remembers_a_dropped_parameter_from_any_run():
    """A parameter the provider refused in one batch makes the whole merged
    measurement non-deterministic, so the flag must not be lost."""
    day1 = _suite(_result("totals-01"), temperature_supported=False)
    day2 = _suite(_result("rates-01"))
    assert report.merge([day1, day2]).temperature_supported is False


def test_merge_refuses_to_mix_models():
    a = _suite(_result("totals-01"))
    b = _suite(_result("rates-01"), model="gemini/gemini-3.1-flash-lite")
    with pytest.raises(ValueError, match="same model"):
        report.merge([a, b])


def test_merge_rejects_an_empty_list():
    with pytest.raises(ValueError, match="no suites"):
        report.merge([])


def test_json_serialises_values_psycopg_returns():
    """Decimal and date are not JSON types; a run must not die at write time."""
    from decimal import Decimal

    suite = _suite(
        _result(
            "totals-01",
            correct=False,
            reference_rows=((Decimal("1.5"), dt.date(2025, 8, 15), None),),
        )
    )
    payload = json.loads(report.to_json([suite]))
    assert payload["suites"][0]["results"][0]["reference_rows"][0][0] == "1.5"


# ---------------------------------------------------------------------------
# Measured cost
# ---------------------------------------------------------------------------


def _priced_suite(prompt_tokens: int, completion_tokens: int, model: str) -> runner.SuiteResult:
    return runner.SuiteResult(
        model=model,
        started_at=dt.datetime(2026, 11, 17, 12, 0, 0, tzinfo=dt.UTC),
        results=(_result("totals-01"),),
        temperature_supported=True,
        reasoning_effort_supported=True,
        retries_used=0,
        seconds=10.0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def test_cost_multiplies_measured_tokens_by_the_price_table():
    suite = _priced_suite(1_000_000, 1_000_000, "gemini/gemini-3.6-flash")
    assert report.cost_usd(suite) == pytest.approx(0.75 + 3.75)


def test_cost_is_none_for_a_model_with_no_published_price():
    suite = _priced_suite(1_000_000, 0, "gemini/gemma-4-31b-it")
    assert report.cost_usd(suite) is None


def test_markdown_prints_measured_tokens_and_cost():
    md = report.to_markdown(
        [_priced_suite(225_000, 20_000, "gemini/gemini-3.6-flash")], threshold=0.70
    )
    assert "225,000" in md
    assert "$" in md


def test_markdown_dates_the_price_it_used():
    """A cost with no as-of date is a number nobody can check later."""
    md = report.to_markdown(
        [_priced_suite(225_000, 20_000, "gemini/gemini-3.6-flash")], threshold=0.70
    )
    assert str(report.PRICING["as_of"]) in md


def test_markdown_reports_tokens_without_a_cost_when_the_price_is_unknown():
    md = report.to_markdown([_priced_suite(225_000, 2_000, "stub/unpriced")], threshold=0.70)
    assert "225,000" in md
    assert "fiyat bilinmiyor" in md


def test_merge_sums_the_token_counts():
    """Batched runs have to add up, or a split run under-reports its cost."""
    a = _priced_suite(100_000, 1_000, "gemini/gemini-3.6-flash")
    b = _priced_suite(50_000, 500, "gemini/gemini-3.6-flash")
    merged = report.merge([a, b])
    assert merged.prompt_tokens == 150_000
    assert merged.completion_tokens == 1_500


def test_from_json_restores_the_token_counts():
    suite = _priced_suite(123_456, 789, "gemini/gemini-3.6-flash")
    restored = report.from_json(report.to_json([suite]))[0]
    assert restored.prompt_tokens == 123_456
    assert restored.completion_tokens == 789
