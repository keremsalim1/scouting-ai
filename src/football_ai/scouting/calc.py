"""Pure math for the player profile: category scores and PAdj.

No DB, no I/O — kept separate from profile.py so the arithmetic is testable
without a database connection.
"""

from __future__ import annotations

# PAdj scales action *volume* with how much the ball the opponent had; it is
# meaningless for a success rate (tackle_pct does not get easier because the
# opponent had the ball more), so only per90/count metrics are adjusted.
# Public because the Day 8 vector build applies the same rule and must not
# restate it.
POSSESSION_ADJUSTABLE_UNITS: frozenset[str] = frozenset({"per90", "count"})


def category_score(percentiles: list[float | None]) -> float | None:
    """Simple mean of the non-null percentiles. None if none are non-null."""
    known = [p for p in percentiles if p is not None]
    if not known:
        return None
    return sum(known) / len(known)


def possession_adjust(value: float, avg_opponent_possession_pct: float | None) -> float | None:
    """PAdj = raw_per90 * 50 / avg_opponent_possession_pct.

    None when the player's average opponent possession is unknown — there is
    nothing to adjust against.
    """
    if avg_opponent_possession_pct is None:
        return None
    return value * 50.0 / avg_opponent_possession_pct
