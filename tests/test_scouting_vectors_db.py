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


def test_python_fine_to_broad_matches_the_sql_function(ro_conn):
    """The Python map duplicates football.position_group_broad(); prove they agree."""
    from football_ai.scouting.broad_groups import FINE_TO_BROAD

    with ro_conn.cursor() as cur:
        cur.execute(
            "select distinct position_group, position_group_broad "
            "from football.player_season where position_group is not null"
        )
        rows = cur.fetchall()
    assert rows
    checked = 0
    for fine, broad in rows:
        if fine not in FINE_TO_BROAD:
            continue  # covered by the next test
        assert FINE_TO_BROAD[fine] == broad
        checked += 1
    assert checked == len(FINE_TO_BROAD)


def test_no_qualified_player_sits_outside_the_vector_spaces(ro_conn):
    """`UNK` (position_source='unknown') has no category set and therefore no
    vector space. That is safe only as long as no such player qualifies - if
    one ever did, the build would KeyError instead of placing him."""
    from football_ai.scouting.broad_groups import FINE_TO_BROAD

    with ro_conn.cursor() as cur:
        cur.execute(
            "select position_group, count(*) from football.player_season "
            "where minutes_played >= 900 and position_group <> all(%s) "
            "group by position_group",
            (list(FINE_TO_BROAD),),
        )
        assert cur.fetchall() == []
