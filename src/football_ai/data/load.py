"""Bulk loading into Postgres.

Two decisions worth knowing:

**COPY, not INSERT.** ``pandas.to_sql`` issues INSERT statements through
SQLAlchemy; every row is parsed and planned individually. COPY is Postgres's
bulk path: one statement, one parse. Measured on 50 000 pass rows via
``scripts/etl.py --benchmark``: COPY 1.01s, to_sql 2.51s, so **2.5x** - real,
but far less than the order of magnitude this choice is usually sold with.

The reason the gap is only 2.5x is that the bottleneck is on our side of the
socket, not the server's. Measured separately: of that 1.01s, ``itertuples``
costs 0.14s and the per-cell ``to_copy_value`` pass another 0.58s, so ~71% of
COPY time is Python converting pandas scalars. Serialising with
``DataFrame.to_csv`` into a buffer instead does the same work 1.9x faster
(0.38s), which would make the whole load roughly 1.5x quicker - 36s to ~24s
for the pass table. Not taken: it trades a modest win for fragile NULL versus
empty-string encoding in text columns. Revisit if load time starts to hurt.

**TRUNCATE inside the transaction, not DELETE or UPSERT.** The 2025/26 season
is finished, so there is no incremental data: a full reload is the honest
model. UPSERT (``on conflict``) is the tool for changing data and would leave
orphans behind if a row ever disappeared from the source. The reason TRUNCATE
is safe here is that in Postgres it is transactional (unlike MySQL): if the
load fails halfway, the rollback puts the old rows back.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd
import psycopg
from psycopg import sql as pgsql

from football_ai.data.extract import TABLE_COLUMNS

SCHEMA = "football"


def to_copy_value(value: object) -> object:
    """Normalise a pandas scalar into something psycopg can adapt.

    pandas hands us ``pd.NA``, ``NaT`` and float ``nan`` for missing data, and
    numpy scalars for everything else. psycopg understands ``None`` and Python
    scalars, so this is the boundary where pandas types are left behind.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    # numpy bool_/int64/float64 all expose .item(); Timestamp does not.
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def copy_dataframe(
    conn: psycopg.Connection,
    table: str,
    frame: pd.DataFrame,
    columns: Sequence[str] | None = None,
) -> int:
    """Stream ``frame`` into ``table`` with COPY. Returns the row count.

    Column order comes from ``TABLE_COLUMNS`` and is named explicitly in the
    COPY statement, so adding a column to the table later cannot silently
    shift values into the wrong column.
    """
    cols = list(columns or TABLE_COLUMNS[table])
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        msg = f"{table}: frame is missing columns {missing}"
        raise ValueError(msg)

    statement = pgsql.SQL("copy {}.{} ({}) from stdin").format(
        pgsql.Identifier(SCHEMA),
        pgsql.Identifier(table),
        pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
    )
    rows = 0
    with conn.cursor() as cur, cur.copy(statement) as copy:
        # itertuples is the fast path: no per-row Series construction.
        for row in frame.loc[:, cols].itertuples(index=False, name=None):
            copy.write_row(tuple(to_copy_value(v) for v in row))
            rows += 1
    return rows


def insert_ignoring_conflicts(
    conn: psycopg.Connection,
    table: str,
    frame: pd.DataFrame,
    columns: Sequence[str] | None = None,
) -> int:
    """Append rows, skipping ones already present. Returns rows actually added.

    This is the opposite strategy to ``truncate`` + ``copy_dataframe``, and the
    difference is the nature of the data, not a preference. The fact tables
    hold a finished season: a full reload is exact. ``data_quality`` holds one
    point per validation run and accumulates, so it is append-only, keyed by
    the report's own timestamp. COPY cannot express "on conflict", so this
    takes the slower INSERT path - fine for tens of rows.
    """
    cols = list(columns or TABLE_COLUMNS[table])
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        msg = f"{table}: frame is missing columns {missing}"
        raise ValueError(msg)

    statement = pgsql.SQL("insert into {}.{} ({}) values ({}) on conflict do nothing").format(
        pgsql.Identifier(SCHEMA),
        pgsql.Identifier(table),
        pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
        pgsql.SQL(", ").join(pgsql.Placeholder() * len(cols)),
    )
    added = 0
    with conn.cursor() as cur:
        for row in frame.loc[:, cols].itertuples(index=False, name=None):
            cur.execute(statement, tuple(to_copy_value(v) for v in row))
            added += cur.rowcount
    return added


def truncate(conn: psycopg.Connection, tables: Sequence[str]) -> None:
    """Empty ``tables`` in one statement.

    One statement rather than a loop: a single TRUNCATE naming every table
    satisfies all the foreign keys between them at once, so no dependency
    ordering is needed and CASCADE (which would also wipe tables added by
    later days) is never required.
    """
    statement = pgsql.SQL("truncate table {}").format(
        pgsql.SQL(", ").join(
            pgsql.SQL("{}.{}").format(pgsql.Identifier(SCHEMA), pgsql.Identifier(t)) for t in tables
        )
    )
    with conn.cursor() as cur:
        cur.execute(statement)


def row_counts(conn: psycopg.Connection, tables: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                pgsql.SQL("select count(*) from {}.{}").format(
                    pgsql.Identifier(SCHEMA), pgsql.Identifier(table)
                )
            )
            row = cur.fetchone()
            counts[table] = int(row[0]) if row else 0
    return counts


def analyze(conn: psycopg.Connection, tables: Sequence[str]) -> None:
    """Refresh planner statistics after a bulk load.

    COPY does not update statistics, so without this the planner still thinks
    every table is empty and will pick nested loops over hash joins for the
    day 3 views.
    """
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                pgsql.SQL("analyze {}.{}").format(pgsql.Identifier(SCHEMA), pgsql.Identifier(table))
            )
