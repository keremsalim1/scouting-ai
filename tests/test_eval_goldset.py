"""Gold set loader validation.

The yaml is the authority for what the benchmark measures, so a typo has to
fail here with the offending question id in the message - not silently produce
a question that is scored against the wrong rules.
"""

from __future__ import annotations

import pytest

from football_ai.evals.sql import goldset


def _q(**over: object) -> dict:
    base = {
        "id": "totals-01",
        "question": "soru",
        "category": "totals",
        "reference_sql": "select 1",
        "order_sensitive": True,
    }
    return {**base, **over}


def test_parse_defaults_optional_fields():
    gs = goldset.parse([_q()])
    q = gs.questions[0]
    assert q.required_columns == ()
    assert q.forbidden == ()
    assert q.notes == ""


def test_duplicate_id_is_rejected():
    with pytest.raises(ValueError, match="totals-01"):
        goldset.parse([_q(), _q()])


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError, match="offside"):
        goldset.parse([_q(category="offside")])


def test_unknown_forbidden_check_is_rejected():
    with pytest.raises(ValueError, match="hand_of_god"):
        goldset.parse([_q(forbidden=["hand_of_god"])])


def test_reference_sql_required_except_unanswerable():
    with pytest.raises(ValueError, match="reference_sql"):
        goldset.parse([_q(reference_sql=None)])

    gs = goldset.parse([_q(id="unans-01", category="unanswerable", reference_sql=None)])
    assert gs.questions[0].scores_correctness is False


def test_scoring_categories_score_correctness():
    assert goldset.parse([_q()]).questions[0].scores_correctness is True


def test_order_sensitive_must_be_stated():
    """Defaulting it would silently change a verdict: a ranking question judged
    order-insensitively passes with the right rows in the wrong order."""
    raw = {k: v for k, v in _q().items() if k != "order_sensitive"}
    with pytest.raises(ValueError, match="order_sensitive"):
        goldset.parse([raw])


def test_select_filters_by_category_and_ids():
    gs = goldset.parse([_q(), _q(id="rates-01", category="rates")])
    assert [q.id for q in gs.select(category="rates")] == ["rates-01"]
    assert [q.id for q in gs.select(ids=("totals-01",))] == ["totals-01"]


def test_select_preserves_the_requested_id_order():
    gs = goldset.parse([_q(), _q(id="rates-01", category="rates")])
    assert [q.id for q in gs.select(ids=("rates-01", "totals-01"))] == [
        "rates-01",
        "totals-01",
    ]


def test_select_rejects_an_unknown_id():
    gs = goldset.parse([_q()])
    with pytest.raises(KeyError, match="nope-99"):
        gs.select(ids=("nope-99",))


def test_select_without_filters_returns_everything():
    gs = goldset.parse([_q(), _q(id="rates-01", category="rates")])
    assert len(gs.select()) == 2


def test_by_category_groups_questions():
    gs = goldset.parse([_q(), _q(id="totals-02"), _q(id="rates-01", category="rates")])
    grouped = gs.by_category()
    assert [q.id for q in grouped["totals"]] == ["totals-01", "totals-02"]
    assert [q.id for q in grouped["rates"]] == ["rates-01"]


def test_get_returns_the_question():
    gs = goldset.parse([_q()])
    assert gs.get("totals-01").question == "soru"


def test_missing_required_field_names_the_question():
    with pytest.raises(ValueError, match="totals-01"):
        goldset.parse([{k: v for k, v in _q().items() if k != "question"}])


def test_empty_gold_set_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        goldset.parse([])


def test_load_reads_a_yaml_file(tmp_path):
    path = tmp_path / "questions.yaml"
    path.write_text(
        "- id: totals-01\n"
        "  question: soru\n"
        "  category: totals\n"
        "  order_sensitive: true\n"
        "  reference_sql: select 1\n",
        encoding="utf-8",
    )
    gs = goldset.load(path)
    assert [q.id for q in gs.questions] == ["totals-01"]


def test_load_rejects_a_yaml_document_that_is_not_a_list(tmp_path):
    path = tmp_path / "questions.yaml"
    path.write_text("questions: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        goldset.load(path)
