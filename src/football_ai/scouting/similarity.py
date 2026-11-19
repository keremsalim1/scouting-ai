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
    no migration), but the vectors are a batch artefact, so an edit there
    invalidates them silently. Two ways that happens, and both are checked:

      * the metric set changed - the vector's dimensions no longer mean what
        the stored ``metric_keys`` say they mean;
      * ``min_minutes`` changed - the key list is byte-identical but the
        population is different, so every z-score, column mean and PCA basis
        was fitted against a group that no longer exists.
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
    if vector_row["min_minutes"] != min_minutes_threshold:
        msg = (
            f"stored vectors were fitted under a min_minutes of "
            f"{vector_row['min_minutes']}, but config/metrics.yaml now says "
            f"{min_minutes_threshold}; the population - and so every z-score - "
            "differs. Run `make build-vectors`"
        )
        raise StaleVectorsError(msg)

    pool_size = _fetch_pool_size(conn, player_id, season, position_group, weighting)
    results = _fetch_neighbours(
        conn,
        player_id,
        season,
        position_group,
        weighting,
        vector_row["vec"],
        min(n, pool_size),
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
            "select vec, dims, metric_keys, imputed_dims, min_minutes "
            "from football.player_vectors "
            "where player_id = %s and comp = %s and season = %s and weighting = %s",
            (player_id, comp, season, weighting),
        )
        return cur.fetchone()


def _fetch_pool_size(
    conn: psycopg.Connection, player_id: int, season: str, position_group: str, weighting: str
) -> int:
    """Candidates after self-exclusion.

    `count(distinct player_id)`, not `count(*)`: a player who changed leagues
    mid-season has two player_season rows and so two vectors, but he is one
    candidate. Counting rows would overstate the pool and disagree with the
    result list, which keeps one row per player.

    Excluded by player_id rather than by row, for the same reason — matching on
    the row alone would return him as his own closest match.

    `comp` is deliberately *not* filtered: cross-league search is the product.
    `season` is, because comparing a player against a different season's
    population is a different question than the caller asked.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select count(distinct player_id) from football.player_vectors "
            "where season = %s and position_group = %s and weighting = %s "
            "and player_id <> %s",
            (season, position_group, weighting, player_id),
        )
        return cur.fetchone()[0]


def _fetch_neighbours(
    conn: psycopg.Connection,
    player_id: int,
    season: str,
    position_group: str,
    weighting: str,
    vec: str,
    limit: int,
) -> list[SimilarPlayer]:
    if limit <= 0:
        return []
    # Ranked entirely inside player_vectors, cut to `limit`, and only then
    # joined to player_season. That view aggregates player_match_stats and runs
    # the position-voting window functions, so it costs ~8x more to materialise
    # than the vector maths does to run: joining it before the limit measured
    # 375ms against 47ms for this shape.
    #
    # DISTINCT ON keeps one row per player_id (a mid-season league changer has
    # two) and forces an ORDER BY starting with player_id, so the similarity
    # ordering happens in the outer query.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            with ranked as (
                select distinct on (player_id)
                       player_id, comp, season, position_group, imputed_dims,
                       1 - (vec <=> %s::vector) as similarity
                from football.player_vectors
                where season = %s and position_group = %s and weighting = %s
                  and player_id <> %s
                order by player_id, vec <=> %s::vector
            ), top as (
                select * from ranked order by similarity desc limit %s
            )
            select t.player_id, t.comp, t.season, t.position_group, t.imputed_dims,
                   t.similarity, s.player, s.teams, s.minutes_played, s.matches
            from top t
            join football.player_season s
              on s.player_id = t.player_id and s.comp = t.comp and s.season = t.season
            order by t.similarity desc
            """,
            (vec, season, position_group, weighting, player_id, vec, limit),
        )
        rows = cur.fetchall()

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
        for row in rows
    ]
