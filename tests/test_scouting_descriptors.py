"""Role descriptors and the combined similarity feature list: pure, no DB."""

from __future__ import annotations

from football_ai.metrics import load
from football_ai.scouting.broad_groups import broad_metric_keys
from football_ai.scouting.descriptors import ROLE_DESCRIPTORS, vector_feature_keys


def test_descriptors_are_not_metrics_in_metrics_yaml():
    """They carry no direction of merit, so they cannot live in metrics.yaml
    without corrupting its higher_is_better contract."""
    metric_keys = {m.key for m in load().metrics}
    assert not set(ROLE_DESCRIPTORS) & metric_keys


def test_feature_keys_are_the_metrics_then_the_descriptors():
    config = load()
    for broad in ("GK", "DEF", "MID", "ATT"):
        metrics = list(broad_metric_keys(broad, config))
        assert list(vector_feature_keys(broad, config)) == metrics + list(ROLE_DESCRIPTORS)


def test_widest_broad_group_sets_the_vector_width():
    from football_ai.scouting.vectors import VECTOR_WIDTH

    config = load()
    widest = max(len(vector_feature_keys(b, config)) for b in ("GK", "DEF", "MID", "ATT"))
    assert widest == VECTOR_WIDTH


def test_measured_feature_counts():
    config = load()
    assert {b: len(vector_feature_keys(b, config)) for b in ("GK", "DEF", "MID", "ATT")} == {
        "GK": 13,
        "DEF": 30,
        "MID": 37,
        "ATT": 26,
    }
