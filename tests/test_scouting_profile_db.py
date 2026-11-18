"""player_profile() against a real, loaded database."""

from __future__ import annotations

import time

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn
from football_ai.scouting.profile import PlayerNotFoundError, player_profile

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
def qualified_player_id(ro_conn):
    """A player_id with minutes_played >= 900 in some comp/season."""
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played >= 900 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no qualified player in the loaded dataset")
    return row


@pytest.fixture
def sub_threshold_player_id(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played < 900 and minutes_played > 0 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no sub-threshold player in the loaded dataset")
    return row


def test_qualified_player_profile_fields_always_present(ro_conn, qualified_player_id):
    player_id, comp, season = qualified_player_id
    profile = player_profile(ro_conn, player_id, comp, season)
    assert profile.minutes_played > 0
    assert profile.position_group
    assert profile.sample_warning is None
    for cat in profile.categories:
        for metric in cat.metrics:
            assert metric.comparison_scope


def test_sub_threshold_player_still_gets_full_profile(ro_conn, sub_threshold_player_id):
    player_id, comp, season = sub_threshold_player_id
    profile = player_profile(ro_conn, player_id, comp, season)
    assert profile.minutes_played > 0
    assert profile.position_group
    assert profile.sample_warning is not None
    for cat in profile.categories:
        for metric in cat.metrics:
            assert metric.comparison_scope == "below_minutes_threshold"
            assert metric.percentile is None


def test_unknown_player_raises(ro_conn):
    with pytest.raises(PlayerNotFoundError):
        player_profile(ro_conn, -1, "Premier League", "2025/26")


def test_profile_completes_under_one_second(ro_conn, qualified_player_id):
    player_id, comp, season = qualified_player_id
    start = time.monotonic()
    player_profile(ro_conn, player_id, comp, season)
    assert time.monotonic() - start < 1.0
