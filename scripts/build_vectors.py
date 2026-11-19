"""Build similarity vectors into football.player_vectors.

    uv run python scripts/build_vectors.py        # full rebuild

Full rebuild in one transaction (TRUNCATE then insert), the same idempotency
posture as the day 2 ETL: running it twice produces identical rows. That is
what lets the PCA components go unstored - they are recomputed deterministically
by football_ai.scouting.vectors.fit_pca.

One vector space per BROAD position group. See
docs/superpowers/specs/2026-11-19-day8-similarity-design.md for why not per
fine group (the acceptance metric would be undefined, and z-scoring inside the
fine group erases the signal it measures).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import numpy as np
import psycopg
from psycopg.rows import dict_row

from football_ai import metrics as mx
from football_ai.console import force_utf8
from football_ai.data.db import connect, etl_dsn
from football_ai.metrics import MetricsConfig
from football_ai.scouting.broad_groups import FINE_TO_BROAD, broad_metric_keys
from football_ai.scouting.calc import POSSESSION_ADJUSTABLE_UNITS, possession_adjust
from football_ai.scouting.vectors import (
    VECTOR_WIDTH,
    fit_pca,
    pad_to,
    role_scale_factors,
)

WEIGHTINGS = ("equal", "role", "pca")


def fetch_rows(conn: psycopg.Connection) -> list[dict]:
    """Every qualified player's metric values, with their opponent possession.

    One bulk query rather than player_profile() per player: that call is ~330ms,
    which over ~1 100 players would be minutes instead of seconds.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select m.comp, m.season, m.player_id, m.position_group,
                   m.position_group_broad, m.metric, m.unit, m.category, m.value,
                   p.avg_opponent_possession_pct
            from football.player_metrics m
            left join football.player_possession p
                   on p.comp = m.comp and p.season = m.season
                  and p.player_id = m.player_id
            """
        )
        return cur.fetchall()


def build_cells(rows: list[dict], config: MetricsConfig) -> dict[str, dict[tuple[str, str], dict]]:
    """Group metric rows into one matrix per (comp, broad) z-scoring cell.

    Returns ``{broad: {(comp, season): {"players": [...], "values": [...],
    "imputed": [...]}}}`` where ``values`` rows follow
    ``broad_metric_keys(broad)`` order and ``imputed`` is a parallel boolean
    mask.
    """
    by_key = {m.key: m for m in config.metrics}
    # (comp, season, player_id) -> {metric: (value, possession)}
    per_player: dict[tuple, dict] = {}
    identity: dict[tuple, dict] = {}
    for row in rows:
        if row["position_group"] not in FINE_TO_BROAD:
            # 'UNK' - position never determined. It has no category set and so
            # no vector space. A db test asserts no qualified player is UNK, so
            # reaching here means that guarantee broke; skip loudly rather than
            # inventing a role.
            print(f"  skipping unplaceable position_group={row['position_group']!r}")
            continue
        key = (row["comp"], row["season"], row["player_id"])
        per_player.setdefault(key, {})[row["metric"]] = row["value"]
        identity.setdefault(
            key,
            {
                "position_group": row["position_group"],
                "position_group_broad": row["position_group_broad"],
                "possession": row["avg_opponent_possession_pct"],
            },
        )

    cells: dict[str, dict[tuple[str, str], dict]] = {}
    for key, values in per_player.items():
        comp, season, player_id = key
        info = identity[key]
        broad = FINE_TO_BROAD[info["position_group"]]
        metric_keys = broad_metric_keys(broad, config)
        possession = info["possession"]

        row_values: list[float] = []
        row_imputed: list[bool] = []
        for metric_key in metric_keys:
            raw = values.get(metric_key)
            if raw is None:
                # Day 4 emits no row for a metric the player never attempted.
                row_values.append(0.0)
                row_imputed.append(True)
                continue
            metric = by_key[metric_key]
            if metric.category == "defending" and metric.unit in POSSESSION_ADJUSTABLE_UNITS:
                adjusted = possession_adjust(raw, possession)
                if adjusted is None:
                    # Possession unknown. Substituting the raw value would mix
                    # adjusted and unadjusted numbers in one distribution and
                    # produce a silently wrong z-score.
                    row_values.append(0.0)
                    row_imputed.append(True)
                    continue
                row_values.append(adjusted)
                row_imputed.append(False)
                continue
            row_values.append(float(raw))
            row_imputed.append(False)

        cell = cells.setdefault(broad, {}).setdefault(
            (comp, season), {"players": [], "values": [], "imputed": []}
        )
        cell["players"].append(
            {
                "comp": comp,
                "season": season,
                "player_id": player_id,
                "position_group": info["position_group"],
                "position_group_broad": info["position_group_broad"],
            }
        )
        cell["values"].append(row_values)
        cell["imputed"].append(row_imputed)
    return cells


def zscore_cell(values: np.ndarray, imputed: np.ndarray) -> np.ndarray:
    """Z-score a cell, holding imputed entries out of the mean and stddev.

    An imputed entry is "we do not know", not "the player did zero of it".
    Letting a run of them into the statistics would drag the distribution
    toward the fill value and shift everyone else's score.
    """
    out = np.zeros_like(values, dtype=float)
    for column in range(values.shape[1]):
        observed = ~imputed[:, column]
        if not observed.any():
            continue
        column_values = values[observed, column]
        mean = column_values.mean()
        stddev = column_values.std(ddof=0)
        if stddev == 0:
            continue
        out[observed, column] = (column_values - mean) / stddev
    return out


def build(conn: psycopg.Connection) -> dict[str, int]:
    config = mx.load()
    cells = build_cells(fetch_rows(conn), config)
    built_at = datetime.now(UTC)
    written: dict[str, int] = {}
    records: list[tuple] = []

    for broad, by_cell in sorted(cells.items()):
        metric_keys = list(broad_metric_keys(broad, config))
        players: list[dict] = []
        zscored: list[np.ndarray] = []
        imputed_counts: list[int] = []

        for _, cell in sorted(by_cell.items()):
            values = np.array(cell["values"], dtype=float)
            imputed = np.array(cell["imputed"], dtype=bool)
            zscored.append(zscore_cell(values, imputed))
            imputed_counts.extend(int(mask.sum()) for mask in imputed)
            players.extend(cell["players"])

        matrix = np.vstack(zscored)
        scales = role_scale_factors(metric_keys, config)
        projection, n_components = fit_pca(matrix)
        per_weighting = {
            "equal": (matrix, len(metric_keys)),
            "role": (matrix * scales, len(metric_keys)),
            "pca": (projection, n_components),
        }

        for weighting in WEIGHTINGS:
            vectors, dims = per_weighting[weighting]
            for player, vector, n_imputed in zip(players, vectors, imputed_counts, strict=True):
                records.append(
                    (
                        player["comp"],
                        player["season"],
                        player["player_id"],
                        player["position_group"],
                        player["position_group_broad"],
                        weighting,
                        str(pad_to(vector, VECTOR_WIDTH).tolist()),
                        dims,
                        metric_keys,
                        n_imputed,
                        built_at,
                    )
                )
        written[broad] = len(players)

    with conn.cursor() as cur:
        cur.execute("truncate football.player_vectors")
        cur.executemany(
            "insert into football.player_vectors (comp, season, player_id, "
            "position_group, position_group_broad, weighting, vec, dims, "
            "metric_keys, imputed_dims, built_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            records,
        )
    conn.commit()
    return written


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    conn = connect(etl_dsn())
    try:
        written = build(conn)
    finally:
        conn.close()
    print("built vectors:")
    for broad, count in sorted(written.items()):
        print(f"  {broad:<4} {count:>5} players x {len(WEIGHTINGS)} weightings")
    print(f"  {'total':<4} {sum(written.values()) * len(WEIGHTINGS):>5} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
