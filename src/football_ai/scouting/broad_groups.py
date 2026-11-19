"""Broad position groups and the metric set each similarity vector space uses.

Day 8 keys its vector spaces on the *broad* group, not the fine one. Fine
groups would make the day's acceptance metric undefined: a CB vector and an
FB vector carry different metrics in different slots, so no cosine exists
between them, and z-scoring inside the fine group centres every group on
zero — erasing the very CB-vs-FB signal that metric measures.

The categories are still sourced from Day 7's ``POSITION_CATEGORIES``, unioned
across the fine groups inside each broad group, so there is no second list to
drift. ``discipline`` stays out because it is already out there.
"""

from __future__ import annotations

from football_ai.metrics import MetricsConfig
from football_ai.scouting.categories import POSITION_CATEGORIES

# Mirrors football.position_group_broad() in
# infra/migrations/002_position_and_season_views.sql. A db test asserts the two
# agree for every position present in the data, because a silent divergence
# would put a player in one vector space and search him in another.
FINE_TO_BROAD: dict[str, str] = {
    "GK": "GK",
    "CB": "DEF",
    "FB": "DEF",
    "DM": "MID",
    "CM": "MID",
    "AM": "MID",
    "W": "ATT",
    "FW": "ATT",
}


def _broad_categories() -> dict[str, tuple[str, ...]]:
    """Union each broad group's fine-group categories, first-seen order."""
    merged: dict[str, list[str]] = {}
    for fine, broad in FINE_TO_BROAD.items():
        bucket = merged.setdefault(broad, [])
        for category in POSITION_CATEGORIES[fine]:
            if category not in bucket:
                bucket.append(category)
    return {broad: tuple(categories) for broad, categories in merged.items()}


BROAD_CATEGORIES: dict[str, tuple[str, ...]] = _broad_categories()


def broad_metric_keys(broad: str, config: MetricsConfig) -> tuple[str, ...]:
    """Metric keys for a broad group's vector space, in metrics.yaml order.

    Order is the vector's dimension order, so it has to be stable: it is what
    ``player_vectors.metric_keys`` records and what the staleness check
    compares against.
    """
    categories = set(BROAD_CATEGORIES[broad])
    return tuple(m.key for m in config.metrics if m.category in categories)
