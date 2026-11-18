"""Position-to-radar-category map: pure, no DB."""

from __future__ import annotations

from football_ai.scouting.categories import POSITION_CATEGORIES

POSITION_GROUPS = {"GK", "CB", "FB", "DM", "CM", "AM", "W", "FW"}
VALID_CATEGORIES = {
    "shooting",
    "creation",
    "passing",
    "progression",
    "defending",
    "duels",
    "discipline",
    "goalkeeping",
}


def test_all_position_groups_present():
    assert set(POSITION_CATEGORIES.keys()) == POSITION_GROUPS


def test_no_category_is_discipline():
    for cats in POSITION_CATEGORIES.values():
        assert "discipline" not in cats


def test_categories_are_known_and_nonempty():
    for cats in POSITION_CATEGORIES.values():
        assert cats
        assert set(cats) <= VALID_CATEGORIES
