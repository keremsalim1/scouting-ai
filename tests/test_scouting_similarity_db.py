"""similar_players() against a real, loaded database with built vectors."""

from __future__ import annotations

import time

import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn, readonly_dsn
from football_ai.scouting import similarity as similarity_module
from football_ai.scouting.profile import PlayerNotFoundError
from football_ai.scouting.similarity import (
    PlayerNotQualifiedError,
    StaleVectorsError,
    similar_players,
)

pytestmark = pytest.mark.db


@pytest.fixture
def writable_conn():
    """A rolled-back transaction, so synthetic rows never outlive the test.

    The assertions run on this same connection: a second connection would not
    see uncommitted rows, and committing them would leave the table dirty for
    every later test.
    """
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _clone_vector_row(conn, player_id, comp, season, *, new_comp=None, new_season=None):
    """Copy a player's vector rows under a different comp or season.

    Mirrors a real shape the one-season dataset cannot produce: a mid-season
    league change (two rows, same fine position group) and a second season.
    """
    with conn.cursor() as cur:
        cur.execute(
            "insert into football.player_vectors "
            "(comp, season, player_id, position_group, position_group_broad, "
            " weighting, vec, dims, metric_keys, imputed_dims, built_at) "
            "select %s, %s, player_id, position_group, position_group_broad, "
            "       weighting, vec, dims, metric_keys, imputed_dims, built_at "
            "from football.player_vectors "
            "where player_id = %s and comp = %s and season = %s",
            (new_comp or comp, new_season or season, player_id, comp, season),
        )
        return cur.rowcount


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


@pytest.fixture
def qualified_player(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played >= 900 and position_group = 'FW' limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no qualified FW in the loaded dataset")
    return row


def test_results_share_the_query_players_fine_position(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=10)
    assert len(result.results) == 10
    assert all(r.position_group == result.position_group for r in result.results)
    assert result.comparison_pool_size > 0


def test_similarity_note_and_attribution_are_present(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season)
    assert result.similarity_note == (
        "Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."
    )
    assert result.data_attribution == "openplay (Noah Bair)"
    assert result.metric_keys


def test_query_player_is_never_his_own_match(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=25)
    ids = [r.player_id for r in result.results]
    assert player_id not in ids
    assert len(ids) == len(set(ids))


def test_n_larger_than_the_pool_returns_the_whole_pool(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=10_000)
    assert len(result.results) == result.comparison_pool_size


def test_every_weighting_runs(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    for weighting in ("equal", "role", "pca"):
        result = similar_players(ro_conn, player_id, comp, season, weighting=weighting)
        assert result.weighting == weighting
        assert result.results


def test_similarity_is_ordered_descending(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    scores = [r.similarity for r in similar_players(ro_conn, player_id, comp, season).results]
    assert scores == sorted(scores, reverse=True)


def test_sub_threshold_player_raises(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played < 900 and minutes_played > 0 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no sub-threshold player in the loaded dataset")
    with pytest.raises(PlayerNotQualifiedError):
        similar_players(ro_conn, *row)


def test_unknown_player_raises(ro_conn):
    with pytest.raises(PlayerNotFoundError):
        similar_players(ro_conn, -1, "eng", "2526")


def test_missing_vector_row_raises_rather_than_returning_nothing(
    ro_conn, qualified_player, monkeypatch
):
    player_id, comp, season = qualified_player
    monkeypatch.setattr(similarity_module, "_fetch_vector_row", lambda *a, **k: None)
    with pytest.raises(StaleVectorsError):
        similar_players(ro_conn, player_id, comp, season)


def test_stale_metric_set_raises(ro_conn, qualified_player, monkeypatch):
    player_id, comp, season = qualified_player
    monkeypatch.setattr(
        similarity_module, "broad_metric_keys", lambda *a, **k: ("a_metric_added_later",)
    )
    with pytest.raises(StaleVectorsError):
        similar_players(ro_conn, player_id, comp, season)


def test_changed_min_minutes_threshold_raises(ro_conn, qualified_player, monkeypatch):
    """The threshold decides who is in the population, so changing it changes
    every z-score, mean and PCA basis while leaving the metric key list
    byte-identical. metrics.yaml is runtime authority; the vectors are not."""
    import dataclasses

    from football_ai.metrics import load

    player_id, comp, season = qualified_player
    relaxed = dataclasses.replace(load(), min_minutes=100)
    monkeypatch.setattr(similarity_module, "load_metrics", lambda *a, **k: relaxed)
    with pytest.raises(StaleVectorsError):
        similar_players(ro_conn, player_id, comp, season)


def test_pool_size_counts_players_not_rows(writable_conn, qualified_player):
    """A mid-season league changer has two vector rows. He is one candidate,
    not two — otherwise the reported pool overstates what was searched."""
    player_id, comp, season = qualified_player
    with writable_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_vectors "
            "where position_group = 'FW' and weighting = 'equal' "
            "and player_id <> %s limit 1",
            (player_id,),
        )
        other_id, other_comp, other_season = cur.fetchone()

    before = similar_players(writable_conn, player_id, comp, season).comparison_pool_size
    assert _clone_vector_row(writable_conn, other_id, other_comp, other_season, new_comp="zzz"), (
        "expected the clone to insert rows"
    )
    after = similar_players(writable_conn, player_id, comp, season).comparison_pool_size
    assert after == before


def test_vectors_from_another_season_are_not_candidates(writable_conn, qualified_player):
    """Only one season is loaded today, so a missing season filter is
    invisible. It would not stay invisible."""
    player_id, comp, season = qualified_player
    with writable_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_vectors "
            "where position_group = 'FW' and weighting = 'equal' "
            "and player_id <> %s limit 1",
            (player_id,),
        )
        other_id, other_comp, other_season = cur.fetchone()

    before = similar_players(writable_conn, player_id, comp, season).comparison_pool_size
    assert _clone_vector_row(
        writable_conn, other_id, other_comp, other_season, new_season="2425"
    ), "expected the clone to insert rows"
    result = similar_players(writable_conn, player_id, comp, season, n=10_000)
    assert result.comparison_pool_size == before
    assert len(result.results) == result.comparison_pool_size


def test_position_consistency_excludes_gk_and_covers_every_other_group(ro_conn):
    from eval_similarity import position_consistency

    scores = position_consistency(ro_conn, "equal")
    assert "GK" not in scores
    assert set(scores) == {"CB", "FB", "DM", "CM", "AM", "W", "FW"}
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_query_completes_under_200ms(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    similar_players(ro_conn, player_id, comp, season)  # warm
    start = time.monotonic()
    similar_players(ro_conn, player_id, comp, season)
    assert time.monotonic() - start < 0.2
