"""Result-set equality: the benchmark's judge.

The rule the whole benchmark rests on: if the model's query returns the same
rows and numbers as the reference, the answer is right, however it was
written. These tests pin what "the same" means - which differences are real
and which are noise from psycopg's type mapping or from a harmless extra
column.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from football_ai.evals.sql import compare


def test_decimal_and_float_compare_within_tolerance():
    assert compare.values_equal(Decimal("1.5"), 1.5)
    assert compare.values_equal(Decimal("0.1") + Decimal("0.2"), 0.30000000000000004)
    assert not compare.values_equal(Decimal("1.5"), 1.6)


def test_integers_and_floats_of_the_same_value_are_equal():
    assert compare.values_equal(11, 11.0)


def test_booleans_do_not_match_numbers():
    """`True == 1` in Python, so a boolean column would silently match a count."""
    assert not compare.values_equal(True, 1)
    assert not compare.values_equal(1, True)
    assert compare.values_equal(True, True)


def test_none_only_equals_none():
    assert compare.values_equal(None, None)
    assert not compare.values_equal(None, 0)
    assert not compare.values_equal(0, None)


def test_strings_compare_exactly():
    assert compare.values_equal("Saka", "Saka")
    assert not compare.values_equal("Saka", "saka")


def test_dates_compare_by_value():
    assert compare.values_equal(dt.date(2025, 8, 15), dt.date(2025, 8, 15))
    assert not compare.values_equal(dt.date(2025, 8, 15), dt.date(2025, 8, 16))


def test_extra_trailing_columns_are_allowed():
    ref = [("Saka", 11)]
    cand = [("Saka", 11, 2400)]
    assert compare.compare(ref, cand, order_sensitive=True).equal


def test_missing_column_is_not_equal():
    assert not compare.compare([("Saka", 11)], [("Saka",)], order_sensitive=True).equal


def test_column_names_are_irrelevant_position_is_not():
    assert not compare.compare([("Saka", 11)], [(11, "Saka")], order_sensitive=True).equal


def test_row_count_mismatch_is_not_equal():
    ref = [("a", 1), ("b", 2)]
    cand = [("a", 1), ("b", 2), ("c", 3)]
    out = compare.compare(ref, cand, order_sensitive=False)
    assert not out.equal
    assert "row count" in out.reason


def test_a_candidate_with_fewer_rows_is_not_equal():
    out = compare.compare([("a", 1), ("b", 2)], [("a", 1)], order_sensitive=True)
    assert not out.equal
    assert "row count" in out.reason


def test_order_matters_only_when_requested():
    ref = [("a", 1), ("b", 2)]
    cand = [("b", 2), ("a", 1)]
    assert not compare.compare(ref, cand, order_sensitive=True).equal
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_order_insensitive_keeps_duplicates():
    assert not compare.compare(
        [("a", 1), ("a", 1)], [("a", 1), ("b", 2)], order_sensitive=False
    ).equal


def test_order_insensitive_sorts_rows_containing_null():
    ref = [("a", None), ("b", 2.0)]
    cand = [("b", 2.0), ("a", None)]
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_order_insensitive_sorts_mixed_types_without_raising():
    ref = [(1, "a"), ("2", None), (dt.date(2025, 1, 1), 3.0)]
    cand = [(dt.date(2025, 1, 1), 3.0), (1, "a"), ("2", None)]
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_order_insensitive_ignores_extra_columns_when_sorting():
    """Sorting must happen on the compared prefix, not the raw candidate row,
    or an extra column could reorder the candidate against the reference."""
    ref = [("a", 1), ("b", 2)]
    cand = [("b", 2, 99), ("a", 1, 1)]
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_both_empty_is_equal():
    assert compare.compare([], [], order_sensitive=True).equal


def test_empty_reference_against_rows_is_not_equal():
    out = compare.compare([], [("a", 1)], order_sensitive=True)
    assert not out.equal
    assert "row count" in out.reason


def test_reason_names_the_first_differing_row():
    out = compare.compare([("a", 1)], [("a", 2)], order_sensitive=True)
    assert not out.equal
    assert "row 1" in out.reason


def test_reason_names_the_differing_column():
    out = compare.compare([("a", 1, 2)], [("a", 1, 3)], order_sensitive=True)
    assert "column 3" in out.reason


def test_equal_comparison_carries_no_reason():
    assert compare.compare([("a", 1)], [("a", 1)], order_sensitive=True).reason == ""


# ---------------------------------------------------------------------------
# Reference columns located within the candidate, not anchored at position 0
# ---------------------------------------------------------------------------


def test_a_leading_identifier_column_does_not_break_the_match():
    """The strong model answered `select player_id, player, count(...)` where
    the reference asks for `player, count(...)`. The information is complete
    and the extra column is leading, not trailing."""
    ref = [("Ademola Lookman", 2)]
    cand = [(104058, "Ademola Lookman", 2, "eng, ita")]
    assert compare.compare(ref, cand, order_sensitive=True).equal


def test_interleaved_extra_columns_are_allowed():
    ref = [("Saka", 11)]
    cand = [("Saka", "Arsenal", 11, 2400, 35)]
    assert compare.compare(ref, cand, order_sensitive=True).equal


def test_the_reference_order_must_be_preserved():
    ref = [("Saka", 11)]
    cand = [(11, "Saka")]
    assert not compare.compare(ref, cand, order_sensitive=True).equal


def test_one_column_mapping_is_used_for_every_row():
    """Picking columns per row would let a candidate match by cherry-picking a
    different column in each row."""
    ref = [("a", 1), ("b", 2)]
    cand = [("a", 1, 99), ("b", 99, 2)]
    assert not compare.compare(ref, cand, order_sensitive=True).equal


def test_a_missing_value_is_still_not_equal():
    ref = [("Saka", 11)]
    cand = [("Saka", "Arsenal", 2400)]
    assert not compare.compare(ref, cand, order_sensitive=True).equal


def test_a_wrong_value_is_still_not_equal():
    ref = [("Saka", 11)]
    cand = [("Saka", "Arsenal", 9, 2400)]
    assert not compare.compare(ref, cand, order_sensitive=True).equal


def test_the_reason_says_which_reference_column_was_not_found():
    out = compare.compare([("Saka", 11)], [("Saka", "Arsenal")], order_sensitive=True)
    assert "column 2" in out.reason


def test_order_insensitive_matching_still_locates_columns():
    ref = [("a", 1), ("b", 2)]
    cand = [(99, "b", 2), (98, "a", 1)]
    assert compare.compare(ref, cand, order_sensitive=False).equal
