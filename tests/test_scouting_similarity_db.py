"""similar_players() against a real, loaded database with built vectors."""

from __future__ import annotations

import time

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn
from football_ai.scouting import similarity as similarity_module
from football_ai.scouting.profile import PlayerNotFoundError
from football_ai.scouting.similarity import (
    PlayerNotQualifiedError,
    StaleVectorsError,
    similar_players,
)

pytestmark = pytest.mark.db


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
