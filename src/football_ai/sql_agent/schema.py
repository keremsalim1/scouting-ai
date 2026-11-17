"""Build the schema description the model sees, from the database itself.

Hand-written schema prompts rot: a column gets renamed in a migration and the
prompt keeps describing the old one, so the model writes SQL that no longer
parses. Everything here is read from the Postgres catalog and from
`metric_definitions`, so the description cannot drift from the database.

Three things make the difference between a model that writes working SQL and
one that guesses:

* **Only the relations the guard allows.** Describing a table the guard will
  refuse wastes a round trip and teaches the model a wrong habit.
* **Foreign keys, written as join hints.** This is why they were declared in
  migration 001 - the generated description is the payoff.
* **The actual literal values of low-cardinality columns.** A model that does
  not know `comp` holds `'eng'` will confidently write
  `where comp = 'Premier League'` and get an empty result, which is worse than
  an error because nothing looks wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from football_ai.data.db import ALLOWED_RELATIONS, SCHEMA

# Columns whose distinct values are few enough to list, and important enough
# that guessing them produces silently empty results.
# KNOWN LIMITATION, and it contradicts D-023's own principle that the schema
# description comes from the catalog rather than from a hand-maintained list:
# this map IS hand-maintained, so a low-cardinality column nobody added stays
# invisible and the model guesses at it. `status_code` was exactly that.
# The proper fix is to discover these from the catalog - `pg_stats.n_distinct`
# is cheap enough to pre-filter with, so only genuinely small columns get a
# `count(distinct)` and `passes` (1.08M rows) is never scanned. Deferred
# rather than done here because it belongs with the day 5 generator, not with
# the day 6 benchmark that found it.
ENUM_LIKE_COLUMNS: dict[str, tuple[str, ...]] = {
    "player_season": ("comp", "season", "position_group", "position_group_broad"),
    "player_per90": ("comp", "season", "position_group", "position_source"),
    "player_metrics": ("comp", "metric", "position_group", "comparison_scope", "unit", "category"),
    "position_map": ("comp", "position", "position_group", "position_source"),
    # `status_code` carries a single value (6) across all 1 140 matches, and
    # day 6 caught the model inventing `status_code = 3` and returning zero
    # rows for "how many La Liga matches were played". An integer that looks
    # like a status enum and whose values are not spelled out is an invitation
    # to guess.
    "matches": ("comp", "season", "status_code", "max_period"),
    "data_quality": ("comp", "metric", "status"),
    "data_quality_features": ("feature", "status"),
}

MAX_LISTED_VALUES = 40

# Types shortened for the prompt: `character varying` and `double precision`
# cost tokens and tell the model nothing it needs.
TYPE_ALIASES = {
    "character varying": "text",
    "double precision": "float",
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
    "integer": "int",
    "bigint": "int",
    "smallint": "int",
    "boolean": "bool",
    "real": "float",
    "numeric": "float",
}


@dataclass(frozen=True)
class Column:
    name: str
    type: str


@dataclass(frozen=True)
class Relation:
    name: str
    kind: str  # 'table' or 'view'
    comment: str | None
    columns: tuple[Column, ...]


def _short_type(sql_type: str) -> str:
    return TYPE_ALIASES.get(sql_type, sql_type)


def read_relations(conn: psycopg.Connection) -> list[Relation]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.relname,
                   case c.relkind when 'v' then 'view' else 'table' end,
                   obj_description(c.oid)
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = %s and c.relkind in ('r', 'v') and c.relname = any(%s)
            order by c.relkind desc, c.relname
            """,
            (SCHEMA, list(ALLOWED_RELATIONS)),
        )
        heads = cur.fetchall()

        cur.execute(
            """
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = %s and table_name = any(%s)
            order by table_name, ordinal_position
            """,
            (SCHEMA, list(ALLOWED_RELATIONS)),
        )
        by_relation: dict[str, list[Column]] = {}
        for table, column, data_type in cur.fetchall():
            by_relation.setdefault(table, []).append(Column(column, _short_type(data_type)))

    return [
        Relation(name=name, kind=kind, comment=comment, columns=tuple(by_relation.get(name, ())))
        for name, kind, comment in heads
    ]


def read_foreign_keys(conn: psycopg.Connection) -> list[tuple[str, str, str, str]]:
    """(child, child_column, parent, parent_column), as join hints."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select child.relname, child_col.attname, parent.relname, parent_col.attname
            from pg_constraint con
            join pg_class child on child.oid = con.conrelid
            join pg_class parent on parent.oid = con.confrelid
            join pg_namespace n on n.oid = child.relnamespace
            join lateral unnest(con.conkey) with ordinality as ck(attnum, ord) on true
            join lateral unnest(con.confkey) with ordinality as pk(attnum, ord)
                 on pk.ord = ck.ord
            join pg_attribute child_col
                 on child_col.attrelid = child.oid and child_col.attnum = ck.attnum
            join pg_attribute parent_col
                 on parent_col.attrelid = parent.oid and parent_col.attnum = pk.attnum
            where con.contype = 'f' and n.nspname = %s
            order by child.relname, child_col.attname
            """,
            (SCHEMA,),
        )
        return [tuple(row) for row in cur.fetchall()]


def read_enum_values(conn: psycopg.Connection) -> dict[tuple[str, str], list[str]]:
    """Distinct values for the low-cardinality columns worth spelling out."""
    values: dict[tuple[str, str], list[str]] = {}
    with conn.cursor() as cur:
        for relation, columns in ENUM_LIKE_COLUMNS.items():
            if relation not in ALLOWED_RELATIONS:
                continue
            for column in columns:
                cur.execute(
                    f"""
                    select distinct {column}::text
                    from {SCHEMA}.{relation}
                    where {column} is not null
                    order by 1
                    limit {MAX_LISTED_VALUES + 1}
                    """
                )
                found = [r[0] for r in cur.fetchall()]
                if found and len(found) <= MAX_LISTED_VALUES:
                    values[(relation, column)] = found
    return values


def read_metrics(conn: psycopg.Connection) -> list[tuple[str, str, str, str, bool]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select key, label, unit, formula, higher_is_better
            from football.metric_definitions order by sort_order
            """
        )
        return [tuple(row) for row in cur.fetchall()]


def describe(conn: psycopg.Connection) -> str:
    """The schema section of the prompt."""
    relations = read_relations(conn)
    fks = read_foreign_keys(conn)
    enums = read_enum_values(conn)
    metrics = read_metrics(conn)

    lines: list[str] = [
        f"PostgreSQL schema `{SCHEMA}`. These are the only readable relations;",
        "anything else is refused before it reaches the database.",
        "",
    ]

    for relation in relations:
        lines.append(f"{relation.kind.upper()} {SCHEMA}.{relation.name}")
        if relation.comment:
            lines.append(f"  -- {' '.join(relation.comment.split())}")
        rendered = ", ".join(f"{c.name} {c.type}" for c in relation.columns)
        lines.append(f"  {rendered}")
        for (rel, column), found in sorted(enums.items()):
            if rel == relation.name:
                lines.append(f"  {column} is one of: {', '.join(repr(v) for v in found)}")
        lines.append("")

    if fks:
        lines += ["Joins (declared foreign keys):"]
        lines += [
            f"  {SCHEMA}.{child}.{child_col} -> {SCHEMA}.{parent}.{parent_col}"
            for child, child_col, parent, parent_col in fks
        ]
        lines.append("")

    if metrics:
        lines += [
            "Metric keys for player_metrics.metric, with the formula behind each.",
            "percentile is already oriented so 100 is best, including where a low",
            "raw value is good (marked 'lower is better').",
            "",
        ]
        for key, label, unit, formula, higher in metrics:
            direction = "" if higher else "  [lower is better]"
            lines.append(f"  {key} ({unit}) = {formula}  -- {label}{direction}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
