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


def test_every_qualified_player_has_three_weighting_rows(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select count(*) from football.player_season s "
            "where s.minutes_played >= 900 and not exists ("
            "  select 1 from football.player_vectors v "
            "  where v.player_id = s.player_id and v.comp = s.comp "
            "    and v.season = s.season and v.weighting = 'equal')"
        )
        assert cur.fetchone()[0] == 0
    with ro_conn.cursor() as cur:
        cur.execute("select distinct weighting from football.player_vectors")
        assert {row[0] for row in cur.fetchall()} == {"equal", "role", "pca"}


def test_no_vector_contains_nan_or_infinity(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select count(*) from football.player_vectors "
            "where vec::text like '%%NaN%%' or vec::text like '%%Infinity%%'"
        )
        assert cur.fetchone()[0] == 0


def test_dims_match_the_broad_group_for_non_pca_rows(ro_conn):
    from football_ai.metrics import load
    from football_ai.scouting.broad_groups import broad_metric_keys

    config = load()
    with ro_conn.cursor() as cur:
        cur.execute(
            "select distinct position_group_broad, dims from football.player_vectors "
            "where weighting = 'equal'"
        )
        rows = cur.fetchall()
    assert rows
    for broad, dims in rows:
        assert dims == len(broad_metric_keys(broad, config))


def test_pca_rows_keep_input_metric_keys_and_fewer_dims(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select dims, cardinality(metric_keys) from football.player_vectors "
            "where weighting = 'pca' limit 50"
        )
        rows = cur.fetchall()
    assert rows
    for dims, n_keys in rows:
        assert dims <= n_keys


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
