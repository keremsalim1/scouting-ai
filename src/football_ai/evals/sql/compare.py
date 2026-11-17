"""Compare two result sets, which is how the benchmark decides correctness.

The judge is the rows, not the SQL: a model that writes a query nothing like
the reference but returns the same players and the same numbers has answered
the question. Comparing SQL text instead would measure agreement with one
person's writing style.

Three rules carry most of the weight, and each exists because of a concrete
way the naive version is wrong:

* **Columns by position, with extra ones allowed.** The model may alias
  `value` as `npxg_per90` and the prompt asks it to return the club and the
  sample size, so the candidate legitimately has more columns than the
  reference. The reference's columns must appear, in order, as a prefix.
  Extra trailing columns are not an error; a missing one is.
* **Numbers within a tolerance.** psycopg maps `numeric` to ``Decimal`` and
  `double precision` to ``float``, so the same per-90 value arrives as two
  different types depending on which relation produced it. ``==`` between
  those is a coin flip on the last bit.
* **Rows sorted only when the question does not care.** A "top 5" answer in
  the wrong order is wrong. For everything else the row order is an artefact
  of the plan, so both sides are sorted - as a multiset, keeping duplicates,
  with a key that never compares ``None`` against a string.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Relative tolerance, floored at 1 so small values are not held to an
# absolute-zero standard. Per-90 rates live around 0.1-5.0 and percentages
# around 0-100; 1e-6 is far tighter than any real difference and far looser
# than float representation noise.
TOLERANCE = 1e-6

_NUMERIC = (int, float, Decimal)


@dataclass(frozen=True)
class Comparison:
    equal: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.equal


def _is_number(value: object) -> bool:
    # bool is a subclass of int, and `True == 1`, which would let a boolean
    # column silently match a count of one.
    return isinstance(value, _NUMERIC) and not isinstance(value, bool)


def values_equal(a: object, b: object) -> bool:
    """Is `a` the same value as `b`, allowing for numeric type and precision?"""
    if a is None or b is None:
        return a is None and b is None
    # Excluding bool from the numeric path is not enough on its own: the `==`
    # fallback would still call `True == 1` a match. A boolean column and a
    # count are different answers, so a type mismatch here is a difference.
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if _is_number(a) and _is_number(b):
        left, right = float(a), float(b)
        return abs(left - right) <= TOLERANCE * max(1.0, abs(right))
    return bool(a == b)


def _sort_key(row: tuple) -> tuple:
    """A total order over heterogeneous cells.

    Sorting rows directly raises ``TypeError`` the moment a column holds both
    ``None`` and a string - which our ratio metrics guarantee, since they
    return NULL on a zero denominator. The key sorts nulls first, then groups
    by type rank so numbers never meet strings in a ``<``, and compares
    anything exotic (dates, intervals) by its text form.
    """
    key: list[tuple[int, int, Any]] = []
    for cell in row:
        if cell is None:
            key.append((0, 0, 0))
        elif _is_number(cell):
            key.append((1, 0, float(cell)))
        elif isinstance(cell, str):
            key.append((1, 1, cell))
        else:
            key.append((1, 2, str(cell)))
    return tuple(key)


def _column_mapping(reference: tuple, candidate: tuple) -> tuple[int, ...] | None:
    """Where each reference column sits in the candidate row, or None.

    Greedy left to right, so the reference's column ORDER is preserved while
    its starting position is not. This is what lets a candidate that answered
    `select player_id, player, count(*)` match a reference of
    `select player, count(*)`: the extra column is leading rather than
    trailing, the information is complete, and anchoring at position 0 would
    call the more informative answer wrong.
    """
    mapping: list[int] = []
    start = 0
    for cell in reference:
        for index in range(start, len(candidate)):
            if values_equal(cell, candidate[index]):
                mapping.append(index)
                start = index + 1
                break
        else:
            return None
    return tuple(mapping)


def _rows_equal(reference: tuple, candidate: tuple, mapping: tuple[int, ...]) -> str | None:
    """Compare one row pair through `mapping`; name the offending column."""
    for position, (expected, source) in enumerate(zip(reference, mapping, strict=True), start=1):
        actual = candidate[source] if source < len(candidate) else None
        if not values_equal(expected, actual):
            return f"column {position}: expected {expected!r}, got {actual!r}"
    return None


def _tie_blocks(rows: list[tuple], tie_columns: tuple[int, ...]) -> list[tuple[int, int]]:
    """Consecutive row ranges that share the same ranking-key values.

    Rows inside such a block are tied, so their relative order is the gold set
    author's habit rather than part of the answer. "The 5 highest-scoring
    matches" has three matches on 7 goals; which of the three is listed first
    is not something the question asks for.
    """
    blocks: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(rows) + 1):
        same = index < len(rows) and all(
            values_equal(rows[index][c], rows[start][c])
            for c in tie_columns
            if c < len(rows[index]) and c < len(rows[start])
        )
        if not same:
            blocks.append((start, index))
            start = index
    return blocks


def compare(
    reference: list[tuple],
    candidate: list[tuple],
    *,
    order_sensitive: bool,
    tie_columns: tuple[int, ...] = (),
) -> Comparison:
    """Is `candidate` the same answer as `reference`?

    `tie_columns` names the reference columns a ranking is ordered by. Rows
    that share those values form a block whose internal order is free, so a
    correct ranking is not failed by an arbitrary tiebreak. Ignored when the
    question is a set (`order_sensitive=False`), where order never mattered.
    """
    if len(reference) != len(candidate):
        return Comparison(
            equal=False,
            reason=f"row count: expected {len(reference)}, got {len(candidate)}",
        )
    if not reference:
        return Comparison(equal=True)

    width = len(reference[0])
    for row in candidate:
        if len(row) < width:
            return Comparison(
                equal=False,
                reason=f"column count: expected at least {width}, got {len(row)}",
            )

    # One mapping for the whole result set. Choosing columns row by row would
    # let a candidate match by cherry-picking a different column in each row,
    # so the mapping is found once and then every row is held to it.
    #
    # Which candidate row it is derived from depends on the question: for a
    # ranking the first row must be the first row, so only that pairing is
    # tried. For a set, any candidate row may correspond to the reference's
    # first, so each is tried until one matches.
    # With tie blocks the candidate's first row may legitimately be a
    # different member of the first block, so every row is a probe there too.
    # The mapping is still verified against every row afterwards.
    probes = candidate[:1] if order_sensitive and not tie_columns else candidate
    mapping = next(
        (m for row in probes if (m := _column_mapping(reference[0], row)) is not None),
        None,
    )
    if mapping is None:
        missing = _first_unmatched(reference[0], candidate[0])
        return Comparison(
            equal=False,
            reason=(
                f"row 1, column {missing}: {reference[0][missing - 1]!r} "
                "is not in the candidate row"
            ),
        )

    left = list(reference)
    right = [tuple(row[i] if i < len(row) else None for i in mapping) for row in candidate]
    if not order_sensitive:
        left = sorted(left, key=_sort_key)
        right = sorted(right, key=_sort_key)
    elif tie_columns:
        # Sort both sides within each tie block. The blocks come from the
        # reference, so a candidate that moved a row across a block boundary
        # still fails: that is a ranking error, not a tie.
        for start, end in _tie_blocks(left, tie_columns):
            left[start:end] = sorted(left[start:end], key=_sort_key)
            right[start:end] = sorted(right[start:end], key=_sort_key)

    for position, (expected_row, actual_row) in enumerate(zip(left, right, strict=True), start=1):
        difference = _rows_equal(expected_row, actual_row, tuple(range(len(expected_row))))
        if difference is not None:
            return Comparison(equal=False, reason=f"row {position}, {difference}")

    return Comparison(equal=True)


def _first_unmatched(reference: tuple, candidate: tuple) -> int:
    """Which reference column (1-based) could not be located."""
    start = 0
    for position, cell in enumerate(reference, start=1):
        for index in range(start, len(candidate)):
            if values_equal(cell, candidate[index]):
                start = index + 1
                break
        else:
            return position
    return len(reference)
