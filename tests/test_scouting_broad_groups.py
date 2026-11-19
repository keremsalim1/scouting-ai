"""Broad-group metric sets: pure, no DB."""

from __future__ import annotations

from football_ai.metrics import load
from football_ai.scouting.broad_groups import (
    BROAD_CATEGORIES,
    FINE_TO_BROAD,
    broad_metric_keys,
)
from football_ai.scouting.categories import POSITION_CATEGORIES


def test_every_fine_group_maps_to_a_broad_group():
    assert set(FINE_TO_BROAD) == set(POSITION_CATEGORIES)
    assert set(FINE_TO_BROAD.values()) == {"GK", "DEF", "MID", "ATT"}


def test_broad_categories_are_the_union_of_their_fine_groups():
    for fine, broad in FINE_TO_BROAD.items():
        assert set(POSITION_CATEGORIES[fine]) <= set(BROAD_CATEGORIES[broad])


def test_measured_dimension_counts():
    config = load()
    assert {b: len(broad_metric_keys(b, config)) for b in BROAD_CATEGORIES} == {
        "GK": 11,
        "DEF": 28,
        "MID": 35,
        "ATT": 24,
    }


def test_metric_keys_follow_yaml_order():
    config = load()
    order = [m.key for m in config.metrics]
    keys = broad_metric_keys("MID", config)
    assert list(keys) == [k for k in order if k in set(keys)]


def test_no_broad_group_includes_discipline():
    for cats in BROAD_CATEGORIES.values():
        assert "discipline" not in cats
