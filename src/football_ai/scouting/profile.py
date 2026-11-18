"""`player_profile()`: a JSON-ready Pydantic snapshot of one player's season.

Day 4's `football.player_metrics` view already carries value + percentile +
comparison scope for every qualified (>= min_minutes) player. A player below
that threshold is not in `player_metrics` at all, so this module falls back
to `football.player_per90`'s raw values for them and marks every metric
`comparison_scope = "below_minutes_threshold"` rather than returning a
partial or empty profile — per CLAUDE.md's "degrade and report" policy.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from football_ai.metrics import MetricsConfig
from football_ai.metrics import load as load_metrics
from football_ai.scouting.calc import category_score, possession_adjust
from football_ai.scouting.categories import POSITION_CATEGORIES

_POSSESSION_UNKNOWN_NOTE = (
    "opponent possession is unknown for this player's matches; "
    "defending metrics are not possession-adjusted"
)


class PlayerNotFoundError(Exception):
    """Raised when (player_id, comp, season) has no row in player_season."""


class MetricValue(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    higher_is_better: bool
    percentile: float | None
    comparison_scope: str
    comparison_comp: str | None
    comparison_group_size: int
    possession_adjusted_value: float | None = None


class CategoryScore(BaseModel):
    category: str
    score: float | None
    metrics: list[MetricValue]


class PlayerProfile(BaseModel):
    player_id: int
    player: str
    teams: str
    comp: str
    season: str
    position_group: str
    position_group_broad: str
    position_source: str
    position_share: float
    minutes_played: int
    matches: int
    min_minutes_threshold: int
    sample_warning: str | None
    avg_opponent_possession_pct: float | None
    possession_adjustment_note: str | None
    radar_categories: list[str]
    categories: list[CategoryScore]
    data_attribution: str = "openplay (Noah Bair)"
    generated_at: datetime


def player_profile(
    conn: psycopg.Connection, player_id: int, comp: str, season: str
) -> PlayerProfile:
    identity = _fetch_identity(conn, player_id, comp, season)
    if identity is None:
        msg = f"no player {player_id} in {comp} {season}"
        raise PlayerNotFoundError(msg)

    metrics_config = load_metrics()
    min_minutes_threshold = metrics_config.min_minutes
    minutes_played = identity["minutes_played"]
    position_group = identity["position_group"]

    avg_opponent_possession_pct = _fetch_avg_opponent_possession(conn, player_id, comp, season)
    possession_adjustment_note = (
        None if avg_opponent_possession_pct is not None else _POSSESSION_UNKNOWN_NOTE
    )

    if minutes_played >= min_minutes_threshold:
        sample_warning = None
        metric_rows = _qualified_metric_rows(conn, player_id, comp, season)
    else:
        sample_warning = (
            f"minutes_played ({minutes_played}) is below the {min_minutes_threshold}-minute "
            "threshold used for percentile comparisons; values below are shown without "
            "a percentile."
        )
        metric_rows = _below_threshold_metric_rows(
            conn, player_id, comp, season, position_group, metrics_config
        )

    metrics_by_category: dict[str, list[MetricValue]] = {}
    for row in metric_rows:
        possession_adjusted_value = (
            possession_adjust(row["value"], avg_opponent_possession_pct)
            if row["category"] == "defending"
            else None
        )
        metric_value = MetricValue(
            key=row["metric"],
            label=row["label"],
            value=row["value"],
            unit=row["unit"],
            higher_is_better=row["higher_is_better"],
            percentile=row["percentile"],
            comparison_scope=row["comparison_scope"],
            comparison_comp=row["comparison_comp"],
            comparison_group_size=row["comparison_group_size"],
            possession_adjusted_value=possession_adjusted_value,
        )
        metrics_by_category.setdefault(row["category"], []).append(metric_value)

    radar_categories = list(POSITION_CATEGORIES[position_group])
    categories = [
        CategoryScore(
            category=category,
            score=category_score([m.percentile for m in metrics_by_category.get(category, [])]),
            metrics=metrics_by_category.get(category, []),
        )
        for category in radar_categories
    ]

    return PlayerProfile(
        player_id=player_id,
        player=identity["player"],
        teams=identity["teams"],
        comp=comp,
        season=season,
        position_group=position_group,
        position_group_broad=identity["position_group_broad"],
        position_source=identity["position_source"],
        position_share=identity["position_share"],
        minutes_played=minutes_played,
        matches=identity["matches"],
        min_minutes_threshold=min_minutes_threshold,
        sample_warning=sample_warning,
        avg_opponent_possession_pct=avg_opponent_possession_pct,
        possession_adjustment_note=possession_adjustment_note,
        radar_categories=radar_categories,
        categories=categories,
        generated_at=datetime.now(UTC),
    )


def _fetch_identity(
    conn: psycopg.Connection, player_id: int, comp: str, season: str
) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select player, teams, position_group, position_group_broad, "
            "position_source, position_share, minutes_played, matches "
            "from football.player_season "
            "where player_id = %s and comp = %s and season = %s",
            (player_id, comp, season),
        )
        return cur.fetchone()


def _fetch_avg_opponent_possession(
    conn: psycopg.Connection, player_id: int, comp: str, season: str
) -> float | None:
    with conn.cursor() as cur:
        cur.execute(
            "select avg_opponent_possession_pct from football.player_possession "
            "where player_id = %s and comp = %s and season = %s",
            (player_id, comp, season),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _qualified_metric_rows(
    conn: psycopg.Connection, player_id: int, comp: str, season: str
) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select metric, label, unit, category, higher_is_better, value, "
            "percentile, comparison_scope, comparison_comp, comparison_group_size "
            "from football.player_metrics "
            "where player_id = %s and comp = %s and season = %s",
            (player_id, comp, season),
        )
        return cur.fetchall()


def _below_threshold_metric_rows(
    conn: psycopg.Connection,
    player_id: int,
    comp: str,
    season: str,
    position_group: str,
    metrics_config: MetricsConfig,
) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select * from football.player_per90 "
            "where player_id = %s and comp = %s and season = %s",
            (player_id, comp, season),
        )
        per90_row = cur.fetchone()
    if per90_row is None:
        return []

    rows: list[dict] = []
    with conn.cursor() as cur:
        for metric in metrics_config.metrics:
            value = per90_row.get(metric.source_column)
            if value is None:
                continue
            cur.execute(
                "select comparison_group_size from football.player_metrics "
                "where comp = %s and position_group = %s and metric = %s limit 1",
                (comp, position_group, metric.key),
            )
            group_row = cur.fetchone()
            rows.append(
                {
                    "metric": metric.key,
                    "label": metric.label,
                    "unit": metric.unit,
                    "category": metric.category,
                    "higher_is_better": metric.higher_is_better,
                    "value": value,
                    "percentile": None,
                    "comparison_scope": "below_minutes_threshold",
                    "comparison_comp": None,
                    "comparison_group_size": group_row[0] if group_row else 0,
                }
            )
    return rows
