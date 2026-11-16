"""Guard-then-execute, without a database.

The branch the db-marked tests never reach is the one that matters most here:
a refused query must stop before any cursor is opened. These tests prove it by
passing something that is not a connection at all - if the code touches it,
the test fails with AttributeError instead of passing.
"""

from __future__ import annotations

import psycopg
import pytest

from football_ai.evals.sql import execute

NOT_A_CONNECTION = object()


class _FakeCursor:
    def __init__(self, columns: tuple[str, ...], rows: list[tuple], error: Exception | None):
        self._columns = columns
        self._rows = rows
        self._error = error
        self.executed: list[str] = []
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        if self._error is not None:
            raise self._error
        self.description = [(name,) for name in self._columns]

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class _FakeConn:
    def __init__(
        self,
        columns: tuple[str, ...] = ("n",),
        rows: list[tuple] | None = None,
        error: Exception | None = None,
    ):
        self.cursor_obj = _FakeCursor(columns, rows if rows is not None else [(1,)], error)
        self.rolled_back = False

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj

    def rollback(self) -> None:
        self.rolled_back = True


def test_run_sql_reports_a_guard_refusal_without_touching_the_connection():
    out = execute.run_sql(NOT_A_CONNECTION, "delete from football.players")
    assert out.ok is False
    assert out.guard_refusal
    assert out.rows == []
    assert out.error is None


def test_run_sql_refuses_an_empty_query():
    out = execute.run_sql(NOT_A_CONNECTION, "")
    assert out.ok is False
    assert out.guard_refusal


def test_run_sql_returns_the_guards_rewrite_not_the_input():
    """The guard adds the missing LIMIT, and the executed statement is its
    rewrite - otherwise the reference would stream 200 rows while the model's
    query returned 10 and the mismatch would be an artefact."""
    conn = _FakeConn()
    out = execute.run_sql(conn, "select 1")
    assert out.ok is True
    assert "LIMIT 200" in out.sql.upper()
    assert "LIMIT 200" in conn.cursor_obj.executed[0].upper()


def test_run_sql_returns_columns_and_rows():
    conn = _FakeConn(columns=("player", "goals"), rows=[("Saka", 11)])
    out = execute.run_sql(conn, "select player, goals from football.player_season")
    assert out.columns == ("player", "goals")
    assert out.rows == [("Saka", 11)]


def test_run_sql_honours_max_rows():
    conn = _FakeConn()
    out = execute.run_sql(conn, "select 1", max_rows=10)
    assert "LIMIT 10" in out.sql.upper()


def test_run_sql_keeps_a_smaller_existing_limit():
    conn = _FakeConn()
    out = execute.run_sql(conn, "select 1 limit 5")
    assert "LIMIT 5" in out.sql.upper()


def test_run_sql_turns_a_database_error_into_a_result():
    conn = _FakeConn(error=psycopg.errors.UndefinedColumn("column q does not exist"))
    out = execute.run_sql(conn, "select q from football.player_season")
    assert out.ok is False
    assert out.error is not None
    assert "does not exist" in out.error
    assert out.guard_refusal is None


def test_run_sql_rolls_back_after_a_database_error():
    """Without this the connection stays in a failed transaction and every
    later question in the run reports the same error."""
    conn = _FakeConn(error=psycopg.errors.UndefinedColumn("boom"))
    execute.run_sql(conn, "select q from football.player_season")
    assert conn.rolled_back is True


def test_run_sql_records_elapsed_time():
    out = execute.run_sql(_FakeConn(), "select 1")
    assert out.seconds >= 0.0


def test_explain_sql_prefixes_explain_and_discards_the_plan():
    conn = _FakeConn(columns=("QUERY PLAN",), rows=[("Seq Scan on players",)])
    out = execute.explain_sql(conn, "select 1")
    assert out.ok is True
    assert conn.cursor_obj.executed[0].upper().startswith("EXPLAIN ")
    assert out.rows == []


def test_explain_sql_reports_an_unknown_column():
    conn = _FakeConn(error=psycopg.errors.UndefinedColumn("column nope does not exist"))
    out = execute.explain_sql(conn, "select nope from football.player_season")
    assert out.ok is False
    assert "does not exist" in out.error


def test_explain_sql_refuses_before_explaining():
    out = execute.explain_sql(NOT_A_CONNECTION, "drop table football.players")
    assert out.ok is False
    assert out.guard_refusal


@pytest.mark.parametrize("runner", [execute.run_sql, execute.explain_sql])
def test_both_entry_points_refuse_a_forbidden_relation(runner):
    out = runner(NOT_A_CONNECTION, "select * from pg_catalog.pg_tables")
    assert out.ok is False
    assert out.guard_refusal
