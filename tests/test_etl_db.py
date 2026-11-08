"""Database-backed tests: the day 2 acceptance criteria, as code.

Marked `db`, so the default `pytest` run (and CI without a database) skips
them. Run with a loaded database:

    make db-up && make migrate && make etl
    uv run pytest -m db
"""

from __future__ import annotations

import psycopg
import pytest

from football_ai.data import extract as ex
from football_ai.data import load as ld
from football_ai.data.db import ALLOWED_TABLES, SCHEMA, connect, etl_dsn, readonly_dsn

pytestmark = pytest.mark.db

# Row counts derived from the parquet source on day 1/2. These are the
# "counts match parquet exactly" criterion, pinned.
EXPECTED_COUNTS = {
    "teams": 60,
    "matches": 1_140,
    "lineups": 49_901,
    "player_match_stats": 35_373,
    "shots": 28_434,
    "passes": 1_083_374,
}


@pytest.fixture(scope="module")
def conn():
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no database: {exc}")
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only database access: {exc}")
    yield connection
    connection.close()


def _scalar(conn: psycopg.Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", sorted(ex.TABLE_COLUMNS))
def test_table_columns_match_the_live_schema(conn, table: str) -> None:
    """TABLE_COLUMNS drives positional COPY, so drift here corrupts loads."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = %s and table_name = %s
            order by ordinal_position
            """,
            (SCHEMA, table),
        )
        live = tuple(r[0] for r in cur.fetchall())
    assert live == ex.TABLE_COLUMNS[table]


def test_allowlist_names_only_tables_that_exist(conn) -> None:
    """Day 5's allowlist must not reference a table that was renamed away."""
    with conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = %s",
            (SCHEMA,),
        )
        live = {r[0] for r in cur.fetchall()}
    assert set(ALLOWED_TABLES) <= live


def test_pgvector_extension_is_installed(conn) -> None:
    assert _scalar(conn, "select count(*) from pg_extension where extname = 'vector'") == 1


# ---------------------------------------------------------------------------
# "Row counts match parquet exactly"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("table", "expected"), sorted(EXPECTED_COUNTS.items()))
def test_row_counts_match_the_source(conn, table: str, expected: int) -> None:
    assert ld.row_counts(conn, [table])[table] == expected


def test_every_league_has_380_matches(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("select comp, count(*) from football.matches group by comp order by comp")
        assert cur.fetchall() == [("eng", 380), ("esp", 380), ("ita", 380)]


def test_teams_are_only_the_twenty_per_league(conn) -> None:
    """The source teams table is global (422 rows); we load only what we use."""
    assert _scalar(conn, "select count(*) from football.teams") == 60


def test_players_table_excludes_the_global_catalogue(conn) -> None:
    """20 782 players exist in the source; only referenced ones are loaded."""
    count = _scalar(conn, "select count(*) from football.players")
    assert 1_500 < count < 5_000


# ---------------------------------------------------------------------------
# "No duplicates on a second run"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "key"),
    [
        ("matches", "match_id"),
        ("lineups", "match_id, player_id"),
        ("player_match_stats", "match_id, player_id"),
        ("shots", "match_id, event_id, event_id_sub"),
        ("passes", "match_id, event_id, event_id_sub"),
        ("teams", "team_id"),
        ("players", "player_id"),
    ],
)
def test_natural_key_has_no_duplicates(conn, table: str, key: str) -> None:
    dupes = _scalar(
        conn,
        f"select count(*) from (select {key} from football.{table} "
        f"group by {key} having count(*) > 1) d",
    )
    assert dupes == 0


# ---------------------------------------------------------------------------
# Cross-table consistency: the checks that catch a wrong load
# ---------------------------------------------------------------------------


def test_lineups_played_equals_player_match_stats_rows(conn) -> None:
    """Verified against the source: `played` is exactly the appearance set."""
    played = _scalar(conn, "select count(*) from football.lineups where played")
    stats = _scalar(conn, "select count(*) from football.player_match_stats")
    assert played == stats


def test_starters_are_22_per_match(conn) -> None:
    assert _scalar(conn, "select count(*) from football.lineups where is_starter") == 1_140 * 22


def test_each_match_has_exactly_two_captains(conn) -> None:
    bad = _scalar(
        conn,
        """
        select count(*) from (
            select match_id from football.lineups
            where is_captain_start group by match_id having count(*) <> 2
        ) d
        """,
    )
    assert bad == 0


def test_no_orphan_foreign_keys(conn) -> None:
    """Declared FKs make this true by construction; the test documents it and
    would catch a future migration that dropped a constraint."""
    orphans = _scalar(
        conn,
        """
        select
            (select count(*) from football.player_match_stats s
             left join football.players p using (player_id) where p.player_id is null)
          + (select count(*) from football.passes s
             left join football.players p using (player_id)
             where s.player_id is not null and p.player_id is null)
          + (select count(*) from football.shots s
             left join football.teams t using (team_id) where t.team_id is null)
        """,
    )
    assert orphans == 0


def test_pass_coordinates_are_inside_the_pitch(conn) -> None:
    """Coordinates are 0-100 by definition; day 1 measured zero violations."""
    bad = _scalar(
        conn,
        """
        select count(*) from football.passes
        where x < 0 or x > 100 or y < 0 or y > 100
           or end_x < 0 or end_x > 100 or end_y < 0 or end_y > 100
        """,
    )
    assert bad == 0


def test_is_completed_agrees_with_outcome(conn) -> None:
    mismatched = _scalar(
        conn,
        "select count(*) from football.passes where is_completed <> (outcome = 'Successful')",
    )
    assert mismatched == 0


def test_score_matches_events_has_no_nulls(conn) -> None:
    """Nullable in the source; the ETL resolves null to true."""
    assert (
        _scalar(conn, "select count(*) from football.matches where score_matches_events is null")
        == 0
    )


def test_data_quality_rows_are_present_and_all_pass(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select status, count(*) from football.data_quality
            where run_at = (select max(run_at) from football.data_quality)
            group by status
            """
        )
        assert cur.fetchall() == [("pass", 18)]


# ---------------------------------------------------------------------------
# Security: the read-only role (day 5 depends on these holding)
# ---------------------------------------------------------------------------


def test_readonly_role_can_select(ro_conn) -> None:
    assert _scalar(ro_conn, "select count(*) from football.teams") == 60


@pytest.mark.parametrize(
    "statement",
    [
        "insert into football.teams (team_id, team) values (-1, 'x')",
        "update football.teams set team = 'x'",
        "delete from football.teams",
        "truncate football.teams",
        "create table football.sneaky (id int)",
        "drop table football.teams",
        "alter table football.teams add column x int",
    ],
)
def test_readonly_role_cannot_write(ro_conn, statement: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), ro_conn.cursor() as cur:
        cur.execute(statement)


def test_readonly_role_cannot_create_objects_in_public(ro_conn) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), ro_conn.cursor() as cur:
        cur.execute("create table public.sneaky (id int)")


def test_readonly_role_has_a_server_side_statement_timeout(ro_conn) -> None:
    """Set on the role, so no client and no injected query can lift it."""
    timeout = _scalar(ro_conn, "show statement_timeout")
    assert timeout not in (None, "0")


def test_readonly_statement_timeout_actually_fires(ro_conn) -> None:
    with pytest.raises(psycopg.errors.QueryCanceled), ro_conn.cursor() as cur:
        cur.execute("select pg_sleep(30)")


def test_readonly_role_is_not_a_superuser(ro_conn) -> None:
    assert _scalar(ro_conn, "select current_setting('is_superuser')") == "off"
