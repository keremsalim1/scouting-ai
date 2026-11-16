"""Run one statement the way the agent would, and report what happened.

Two things make this more than a cursor wrapper:

* **Both sides go through the same guard.** The guard adds a missing `LIMIT`,
  so applying it to only one side of a comparison would make the reference
  return 200 rows against the model's 10 and the mismatch would be an
  artefact of the harness, not an answer. `Execution.sql` is always the
  statement that actually ran.
* **A failure is a result, not an exception.** A benchmark whose run dies on
  question 23 because the model invented a column has measured nothing. Guard
  refusals and database errors are reported as fields so the suite continues
  and the report can say which of the two happened.

`explain_sql` exists for CI: `EXPLAIN` validates a query against the real
schema without needing a single row, so a migration that renames a column
breaks the gold set on a database that was only migrated, never loaded.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field

import psycopg

from football_ai.sql_agent import guard


@dataclass(frozen=True)
class Execution:
    """What came back. `ok` means the statement ran; it says nothing about
    whether the answer was right."""

    ok: bool
    columns: tuple[str, ...] = ()
    rows: list[tuple] = field(default_factory=list)
    sql: str | None = None
    error: str | None = None
    guard_refusal: str | None = None
    seconds: float = 0.0

    def __bool__(self) -> bool:
        return self.ok


def _validated(sql: str, max_rows: int) -> tuple[str | None, Execution | None]:
    """Guard `sql`, returning either the rewrite or a refusal Execution."""
    verdict = guard.validate(sql, max_rows=max_rows)
    if not verdict.ok or verdict.sql is None:
        return None, Execution(ok=False, guard_refusal=verdict.reason)
    return verdict.sql, None


def _execute(
    conn: psycopg.Connection,
    statement: str,
    safe_sql: str,
    *,
    keep_rows: bool,
) -> Execution:
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
            description = cur.description
            columns = tuple(col[0] for col in description) if description else ()
            rows = cur.fetchall() if keep_rows and description else []
    except psycopg.Error as exc:
        # The connection is in a failed transaction now. Without the rollback
        # every later question in the run reports this same error, and the
        # report blames the model for a state the harness left behind.
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
        return Execution(
            ok=False,
            sql=safe_sql,
            error=str(exc).strip(),
            seconds=time.perf_counter() - started,
        )

    return Execution(
        ok=True,
        columns=columns,
        rows=list(rows),
        sql=safe_sql,
        seconds=time.perf_counter() - started,
    )


def run_sql(
    conn: psycopg.Connection,
    sql: str,
    *,
    max_rows: int = guard.DEFAULT_LIMIT,
) -> Execution:
    """Validate and run `sql`, returning its rows."""
    safe_sql, refusal = _validated(sql, max_rows)
    if refusal is not None:
        return refusal
    assert safe_sql is not None
    return _execute(conn, safe_sql, safe_sql, keep_rows=True)


def explain_sql(
    conn: psycopg.Connection,
    sql: str,
    *,
    max_rows: int = guard.DEFAULT_LIMIT,
) -> Execution:
    """Validate `sql` against the live schema without reading any data.

    The plan rows are discarded: the only question asked here is whether
    Postgres accepts the statement.
    """
    safe_sql, refusal = _validated(sql, max_rows)
    if refusal is not None:
        return refusal
    assert safe_sql is not None
    return _execute(conn, f"EXPLAIN {safe_sql}", safe_sql, keep_rows=False)
