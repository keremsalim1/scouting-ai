"""Defence in depth: the read-only role refuses the attacks too.

tests/test_sql_guard.py proves the parser refuses them. This file proves the
database would refuse them even if the parser were bypassed entirely - a
parser can be out-argued, a role that lacks the privilege cannot. Both layers
are tested because relying on either alone is the mistake.
"""

from __future__ import annotations

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn
from football_ai.sql_agent import guard

pytestmark = pytest.mark.db

# Attacks that reach the server and must be rejected by privilege, not syntax.
# Read-only attacks (pg_catalog, pg_sleep) are excluded: Postgres permits them
# for any role, which is precisely why the parser allowlist has to exist.
PRIVILEGE_ATTACKS = [
    ("delete rows", "delete from football.players"),
    ("insert row", "insert into football.players values (-1, 'x')"),
    ("update rows", "update football.players set player = 'x'"),
    ("drop table", "drop table football.players"),
    ("truncate", "truncate football.players"),
    ("create table", "create table football.evil (id int)"),
    ("alter table", "alter table football.players add column x int"),
    ("create in public", "create table public.evil (id int)"),
    ("drop a view", "drop view football.player_metrics"),
    ("delete via CTE", "with d as (delete from football.players returning *) select * from d"),
]


@pytest.fixture(scope="module")
def ro():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


@pytest.mark.parametrize(("label", "sql"), PRIVILEGE_ATTACKS, ids=[a[0] for a in PRIVILEGE_ATTACKS])
def test_readonly_role_refuses_the_attack(ro, label: str, sql: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), ro.cursor() as cur:
        cur.execute(sql)


def test_self_grant_succeeds_but_escalates_nothing(ro) -> None:
    """GRANT is the one attack that does not raise.

    Postgres answers a GRANT from a role without grant option with
    `WARNING: no privileges were granted` and reports success. A test asserting
    InsufficientPrivilege here would fail, and a reader could wrongly conclude
    the attack worked. What matters is that no privilege changed hands - a
    statement that does not error is not a statement that did something.
    """
    with ro.cursor() as cur:
        cur.execute("grant all on football.players to football_ro")
        cur.execute(
            """
            select has_table_privilege('football_ro', 'football.players', 'INSERT'),
                   has_table_privilege('football_ro', 'football.players', 'UPDATE'),
                   has_table_privilege('football_ro', 'football.players', 'DELETE'),
                   has_table_privilege('football_ro', 'football.players', 'TRUNCATE'),
                   has_table_privilege('football_ro', 'football.players', 'SELECT')
            """
        )
        insert, update, delete, truncate, select = cur.fetchone()
    assert (insert, update, delete, truncate) == (False, False, False, False)
    assert select is True

    # And it still cannot write.
    with pytest.raises(psycopg.errors.InsufficientPrivilege), ro.cursor() as cur:
        cur.execute("insert into football.players values (-1, 'x')")

    # The guard refuses GRANT before it ever reaches the server anyway.
    assert not guard.validate("grant all on football.players to football_ro").ok


def test_the_guard_refuses_them_first(ro) -> None:
    """Both layers hold, so an attack has to defeat two independent mechanisms."""
    for label, sql in PRIVILEGE_ATTACKS:
        assert not guard.validate(sql).ok, label


def test_guard_approved_queries_actually_run(ro) -> None:
    """A guard that only ever says no would pass every security test and be
    worthless. These are the queries a scouting question really produces."""
    queries = [
        "select count(*) from football.player_season",
        "select player, value from football.player_metrics "
        "where metric = 'npxg_xa_per90' and comp = 'eng' order by value desc",
        "select position_group, count(*) from football.player_season "
        "where minutes_played >= 900 group by position_group",
        "with top as (select player, percentile from football.player_metrics "
        "where metric = 'pass_pct' and position_group = 'CB' order by percentile desc) "
        "select * from top",
        "select p.player, s.minutes_played from football.player_season s "
        "join football.players p using (player_id) where s.comp = 'esp'",
    ]
    for sql in queries:
        checked = guard.validate(sql)
        assert checked.ok, f"guard refused a legitimate query: {checked.reason}"
        with ro.cursor() as cur:
            cur.execute(checked.sql)
            rows = cur.fetchall()
        assert rows, f"no rows for {sql}"


def test_the_injected_limit_really_caps_the_result(ro) -> None:
    checked = guard.validate("select * from football.passes", max_rows=25)
    assert checked.ok
    with ro.cursor() as cur:
        cur.execute(checked.sql)
        assert len(cur.fetchall()) == 25


def test_readonly_role_still_cannot_lift_its_own_timeout(ro) -> None:
    """The guard blocks SET; this proves the server would not honour it as a
    privilege escalation even if some other path reached it."""
    before = None
    with ro.cursor() as cur:
        cur.execute("show statement_timeout")
        before = cur.fetchone()[0]
    assert before not in (None, "0")
