"""Possession-proxy views against a real, loaded database."""

from __future__ import annotations

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_match_possession_sums_to_100(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select team_possession_pct + opponent_possession_pct "
            "from football.match_possession limit 500"
        )
        rows = cur.fetchall()
    assert rows, "expected at least one match_possession row"
    for (total,) in rows:
        assert abs(total - 100.0) < 0.01


def test_player_possession_is_within_bounds(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select avg_opponent_possession_pct from football.player_possession "
            "where avg_opponent_possession_pct is not null limit 500"
        )
        rows = cur.fetchall()
    assert rows, "expected at least one player_possession row"
    for (pct,) in rows:
        assert 0.0 <= pct <= 100.0
