"""`similar_players()`: who else plays like this player.

Cosine over z-scored vectors compares the *pattern* of deviations, not their
magnitude: a player +2 SD across the board and one +1 SD across the board point
in nearly the same direction. That is deliberate, and it is what makes the
mandatory note true rather than decorative — this answers "plays like", never
"is better than".

Candidates are filtered to the query player's fine position group. The vector
space itself is keyed on the broad group, which is what the day 8 evaluation
needs in order to be able to fail; see the design doc.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from football_ai.metrics import load as load_metrics
from football_ai.scouting.broad_groups import FINE_TO_BROAD, broad_metric_keys
from football_ai.scouting.profile import PlayerNotFoundError

SIMILARITY_NOTE = "Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."


class PlayerNotQualifiedError(Exception):
    """Raised when the query player is below the minimum-minutes threshold.

    A per-90 rate from 200 minutes is noise, and a "most similar players" list
    built on noise is the silent wrongness the project's data policy forbids.
    """


class StaleVectorsError(Exception):
    """Raised when player_vectors is missing or no longer matches metrics.yaml.

    config/metrics.yaml is runtime authority (day 4: changing a threshold needs
    no migration), but the vectors are a batch artefact. Adding a metric
    therefore invalidates stored z-scores silently - so this refuses instead.
    """


class SimilarPlayer(BaseModel):
    player_id: int
    player: str
    teams: str
    comp: str
    season: str
    position_group: str
    minutes_played: int
    matches: int
    similarity: float
    imputed_dimensions: int


class SimilarityResult(BaseModel):
    query_player_id: int
    query_player: str
    comp: str
    season: str
    position_group: str
    weighting: str
    comparison_pool_size: int
    min_minutes_threshold: int
    imputed_dimensions: int
    metric_keys: list[str]
    results: list[SimilarPlayer]
    similarity_note: str = SIMILARITY_NOTE
    data_attribution: str = "openplay (Noah Bair)"
    generated_at: datetime


def similar_players(
    conn: psycopg.Connection,
    player_id: int,
    comp: str,
    season: str,
    n: int = 10,
    weighting: str = "equal",
) -> SimilarityResult:
    identity = _fetch_identity(conn, player_id, comp, season)
    if identity is None:
        msg = f"no player {player_id} in {comp} {season}"
        raise PlayerNotFoundError(msg)

    config = load_metrics()
    min_minutes_threshold = config.min_minutes
    minutes_played = identity["minutes_played"]
    if minutes_played < min_minutes_threshold:
        msg = (
            f"player {player_id} played {minutes_played} minutes, below the "
            f"{min_minutes_threshold}-minute threshold; per-90 rates from that "
            "sample are too noisy to rank similarity on"
        )
        raise PlayerNotQualifiedError(msg)

    vector_row = _fetch_vector_row(conn, player_id, comp, season, weighting)
    if vector_row is None:
        msg = (
            f"no {weighting!r} vector for player {player_id} in {comp} {season}; "
            "run `make build-vectors`"
        )
        raise StaleVectorsError(msg)

    position_group = identity["position_group"]
    expected_keys = list(broad_metric_keys(FINE_TO_BROAD[position_group], config))
    if list(vector_row["metric_keys"]) != expected_keys:
        msg = (
            "stored vectors were built from a different metric set than "
            "config/metrics.yaml defines now; run `make build-vectors`"
        )
        raise StaleVectorsError(msg)

    pool_size = _fetch_pool_size(conn, player_id, position_group, weighting)
    results = _fetch_neighbours(
        conn, player_id, position_group, weighting, vector_row["vec"], min(n, pool_size)
    )

    return SimilarityResult(
        query_player_id=player_id,
        query_player=identity["player"],
        comp=comp,
        season=season,
        position_group=position_group,
        weighting=weighting,
        comparison_pool_size=pool_size,
        min_minutes_threshold=min_minutes_threshold,
        imputed_dimensions=vector_row["imputed_dims"],
        metric_keys=expected_keys,
        results=results,
        generated_at=datetime.now(UTC),
    )


def _fetch_identity(
    conn: psycopg.Connection, player_id: int, comp: str, season: str
) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select player, position_group, minutes_played "
            "from football.player_season "
            "where player_id = %s and comp = %s and season = %s",
            (player_id, comp, season),
        )
        return cur.fetchone()


def _fetch_vector_row(
    conn: psycopg.Connection, player_id: int, comp: str, season: str, weighting: str
) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select vec, dims, metric_keys, imputed_dims from football.player_vectors "
            "where player_id = %s and comp = %s and season = %s and weighting = %s",
            (player_id, comp, season, weighting),
        )
        return cur.fetchone()


def _fetch_pool_size(
    conn: psycopg.Connection, player_id: int, position_group: str, weighting: str
) -> int:
    """Candidates after self-exclusion.

    Excluded by player_id rather than by row: a player who changed leagues
    mid-season has two player_season rows and so two vectors, and matching on
    the row alone would return him as his own closest match.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from football.player_vectors "
            "where position_group = %s and weighting = %s and player_id <> %s",
            (position_group, weighting, player_id),
        )
        return cur.fetchone()[0]


def _fetch_neighbours(
    conn: psycopg.Connection,
    player_id: int,
    position_group: str,
    weighting: str,
    vec: str,
    limit: int,
) -> list[SimilarPlayer]:
    if limit <= 0:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select distinct on (v.player_id)
                   v.player_id, v.comp, v.season, v.position_group,
                   v.imputed_dims, s.player, s.teams, s.minutes_played, s.matches,
                   1 - (v.vec <=> %s::vector) as similarity
            from football.player_vectors v
            join football.player_season s
              on s.player_id = v.player_id and s.comp = v.comp and s.season = v.season
            where v.position_group = %s and v.weighting = %s and v.player_id <> %s
            order by v.player_id, v.vec <=> %s::vector
            """,
            (vec, position_group, weighting, player_id, vec),
        )
        rows = cur.fetchall()

    # DISTINCT ON keeps one row per player_id (a league-changer has two), but it
    # forces an ORDER BY starting with player_id, so the final ranking is done
    # here rather than in SQL.
    rows.sort(key=lambda r: r["similarity"], reverse=True)
    return [
        SimilarPlayer(
            player_id=row["player_id"],
            player=row["player"],
            teams=row["teams"],
            comp=row["comp"],
            season=row["season"],
            position_group=row["position_group"],
            minutes_played=row["minutes_played"],
            matches=row["matches"],
            similarity=row["similarity"],
            imputed_dimensions=row["imputed_dims"],
        )
        for row in rows[:limit]
    ]
