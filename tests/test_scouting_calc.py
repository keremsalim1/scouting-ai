"""Category-score averaging and possession-adjustment math: pure, no DB."""

from __future__ import annotations

from football_ai.scouting.calc import category_score, possession_adjust


def test_category_score_averages_non_null():
    assert category_score([80.0, 60.0, 40.0]) == 60.0


def test_category_score_excludes_nulls_from_average():
    assert category_score([80.0, None, 20.0]) == 50.0


def test_category_score_all_null_is_none():
    assert category_score([None, None]) is None


def test_category_score_empty_is_none():
    assert category_score([]) is None


def test_possession_adjust_applies_formula():
    assert possession_adjust(2.0, 60.0) == 2.0 * 50.0 / 60.0


def test_possession_adjust_none_when_possession_unknown():
    assert possession_adjust(2.0, None) is None
