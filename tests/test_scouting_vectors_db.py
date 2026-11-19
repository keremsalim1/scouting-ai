"""Similarity vectors against a real, loaded database."""

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


def test_player_vectors_is_readable_and_has_expected_columns(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'football' and table_name = 'player_vectors'"
        )
        columns = {row[0] for row in cur.fetchall()}
    assert {
        "comp",
        "season",
        "player_id",
        "position_group",
        "position_group_broad",
        "weighting",
        "vec",
        "dims",
        "metric_keys",
        "imputed_dims",
        "built_at",
    } <= columns


def test_vec_column_is_pgvector_of_width_35(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select atttypmod from pg_attribute "
            "where attrelid = 'football.player_vectors'::regclass and attname = 'vec'"
        )
        assert cur.fetchone()[0] == 35
