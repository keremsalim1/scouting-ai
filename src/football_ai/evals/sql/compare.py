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


def _rows_equal(reference: tuple, candidate: tuple) -> str | None:
    """Compare one row pair; return the offending column, or None if equal."""
    for index, (expected, actual) in enumerate(zip(reference, candidate, strict=True), start=1):
        if not values_equal(expected, actual):
            return f"column {index}: expected {expected!r}, got {actual!r}"
    return None


def compare(
    reference: list[tuple],
    candidate: list[tuple],
    *,
    order_sensitive: bool,
) -> Comparison:
    """Is `candidate` the same answer as `reference`?"""
    if len(reference) != len(candidate):
        return Comparison(
            equal=False,
            reason=f"row count: expected {len(reference)}, got {len(candidate)}",
        )
    if not reference:
        return Comparison(equal=True)

    width = len(reference[0])
    trimmed: list[tuple] = []
    for row in candidate:
        if len(row) < width:
            return Comparison(
                equal=False,
                reason=f"column count: expected at least {width}, got {len(row)}",
            )
        trimmed.append(tuple(row[:width]))

    left, right = list(reference), trimmed
    if not order_sensitive:
        # Sorting happens on the trimmed prefix, not the raw candidate row, so
        # an extra trailing column cannot reorder one side against the other.
        left = sorted(left, key=_sort_key)
        right = sorted(right, key=_sort_key)

    for position, (expected_row, actual_row) in enumerate(zip(left, right, strict=True), start=1):
        if len(expected_row) != len(actual_row):
            return Comparison(
                equal=False,
                reason=f"row {position}: column count differs",
            )
        difference = _rows_equal(expected_row, actual_row)
        if difference is not None:
            return Comparison(equal=False, reason=f"row {position}, {difference}")

    return Comparison(equal=True)
