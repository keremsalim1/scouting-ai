"""The gold set against a real database.

These tests deliberately contain no assertions of their own beyond the exit
code: every check lives in scripts/eval_sql_gold.py, which is also what CI
runs. Repeating the assertions here would give two implementations that agree
today and drift the first time one of them gains a check.

The split is by what each needs:
  * `main([])`        - schema only. CI runs exactly this against a migrated,
                        empty database, so a renamed column fails a pull
                        request without an OpenPlay download.
  * `main(["--execute"])` - needs loaded data: every reference returns rows,
                        and no ranking question cuts on a tie.
"""

from __future__ import annotations

import eval_sql_gold
import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn
from football_ai.evals.sql import execute, goldset
from football_ai.sql_agent import guard

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    """Same pattern as tests/test_sql_guard_db.py: skip rather than fail when
    the database is not reachable."""
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_gold_script_passes_the_schema_checks():
    """What CI runs: guard, EXPLAIN, few-shot overlap, counts, self-consistency."""
    assert eval_sql_gold.main([]) == 0


def test_gold_script_passes_the_data_checks():
    """Every reference returns rows and no ranking cuts on a tie."""
    assert eval_sql_gold.main(["--execute"]) == 0


def test_every_reference_runs_as_the_read_only_role(ro_conn):
    """The eval must not need more privilege than the agent has.

    Running the benchmark as the owner would measure something the agent
    cannot actually do.
    """
    broken = [
        (q.id, execute.run_sql(ro_conn, q.reference_sql).error)
        for q in goldset.load().questions
        if q.reference_sql and not execute.run_sql(ro_conn, q.reference_sql).ok
    ]
    assert broken == []


def test_the_guards_limit_does_not_truncate_any_reference(ro_conn):
    """A reference whose own LIMIT exceeds the guard's would be silently cut,
    and the model's shorter answer would then be scored correct."""
    truncated = []
    for q in goldset.load().questions:
        if not q.reference_sql:
            continue
        rows = execute.run_sql(ro_conn, q.reference_sql).rows
        if len(rows) >= guard.DEFAULT_LIMIT:
            truncated.append((q.id, len(rows)))
    assert truncated == []
