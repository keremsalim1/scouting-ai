"""Unit tests for config/metrics.yaml and its validator.

The yaml is loaded into the database and drives how percentiles are oriented,
so a bad entry must fail loudly at load time rather than quietly produce a
metric that ranks the wrong way round.
"""

from __future__ import annotations

import copy

import pytest

from football_ai import metrics as mx

MINIMAL = {
    "version": 1,
    "defaults": {"min_minutes": 900},
    "percentile": {
        "method": "midrank",
        "min_group_size": 20,
        "fallback": "pool_leagues_keep_role",
    },
    "categories": {"shooting": "Bitiricilik"},
    "metrics": [
        {
            "key": "npxg_per90",
            "column": "npxg_per90",
            "label": "npxG / 90",
            "definition": "Penaltı harici beklenen gol.",
            "formula": "Σ npxg / Σ minutes_played × 90",
            "unit": "per90",
            "higher_is_better": True,
            "category": "shooting",
        }
    ],
}


def _doc(**overrides) -> dict:
    doc = copy.deepcopy(MINIMAL)
    doc.update(overrides)
    return doc


def _with_metric(**changes) -> dict:
    doc = copy.deepcopy(MINIMAL)
    doc["metrics"][0].update(changes)
    return doc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_parses_a_valid_document() -> None:
    cfg = mx.parse(copy.deepcopy(MINIMAL))
    assert cfg.min_minutes == 900
    assert cfg.min_group_size == 20
    assert cfg.keys == {"npxg_per90"}
    metric = cfg.metrics[0]
    assert metric.source_column == "npxg_per90"
    assert metric.higher_is_better is True
    assert metric.sort_order == 0


@pytest.mark.parametrize("field", mx.REQUIRED_FIELDS)
def test_every_required_metric_field_is_enforced(field: str) -> None:
    doc = copy.deepcopy(MINIMAL)
    del doc["metrics"][0][field]
    with pytest.raises(ValueError, match=field):
        mx.parse(doc)


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(ValueError, match="unit"):
        mx.parse(_with_metric(unit="per_match"))


def test_category_must_be_declared() -> None:
    with pytest.raises(ValueError, match="category"):
        mx.parse(_with_metric(category="vibes"))


def test_higher_is_better_must_be_a_boolean() -> None:
    """'false' as a string is truthy, which would silently invert a metric."""
    with pytest.raises(ValueError, match="higher_is_better"):
        mx.parse(_with_metric(higher_is_better="false"))


def test_duplicate_keys_are_rejected() -> None:
    doc = copy.deepcopy(MINIMAL)
    doc["metrics"].append(copy.deepcopy(doc["metrics"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        mx.parse(doc)


def test_unknown_percentile_method_is_rejected() -> None:
    doc = _doc()
    doc["percentile"]["method"] = "percent_rank"
    with pytest.raises(ValueError, match="method"):
        mx.parse(doc)


def test_unknown_fallback_is_rejected() -> None:
    doc = _doc()
    doc["percentile"]["fallback"] = "widen_role"
    with pytest.raises(ValueError, match="fallback"):
        mx.parse(doc)


def test_group_size_below_two_is_rejected() -> None:
    doc = _doc()
    doc["percentile"]["min_group_size"] = 1
    with pytest.raises(ValueError, match="min_group_size"):
        mx.parse(doc)


def test_empty_metric_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="no metrics"):
        mx.parse(_doc(metrics=[]))


def test_definition_whitespace_is_normalised() -> None:
    """YAML folded scalars arrive with newlines; the database should get prose."""
    cfg = mx.parse(_with_metric(definition="bir\n  iki   üç\n"))
    assert cfg.metrics[0].definition == "bir iki üç"


# ---------------------------------------------------------------------------
# The real file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real() -> mx.MetricsConfig:
    return mx.load()


def test_real_file_loads(real: mx.MetricsConfig) -> None:
    assert len(real.metrics) >= 30
    assert real.percentile_method == "midrank"
    assert real.fallback == "pool_leagues_keep_role"


def test_every_metric_states_a_formula_and_unit(real: mx.MetricsConfig) -> None:
    """Day 4 acceptance: formula, unit and direction present for every metric."""
    for m in real.metrics:
        assert m.formula.strip(), m.key
        assert m.unit in mx.VALID_UNITS, m.key
        assert isinstance(m.higher_is_better, bool), m.key
        assert m.definition.strip(), m.key
        assert m.label.strip(), m.key


def test_lower_is_better_metrics_are_the_expected_ones(real: mx.MetricsConfig) -> None:
    """Pins the direction flags: an accidental flip silently inverts a radar."""
    lower = {m.key for m in real.metrics if not m.higher_is_better}
    assert lower == {
        "miscontrols_per90",
        "dispossessed_per90",
        "fouls_committed_per90",
        "errors_per90",
    }


def test_percent_metrics_are_named_consistently(real: mx.MetricsConfig) -> None:
    for m in real.metrics:
        if m.unit == "percent":
            assert m.key.endswith("_pct"), m.key
        if m.key.endswith("_per90"):
            assert m.unit == "per90", m.key


def test_config_values_are_what_the_view_reads(real: mx.MetricsConfig) -> None:
    assert set(real.config_values) == {"min_minutes", "min_group_size"}
    assert real.config_values["min_minutes"] == 900.0
    assert real.config_values["min_group_size"] == 20.0
