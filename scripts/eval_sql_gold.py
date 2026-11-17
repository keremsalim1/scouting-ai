"""Validate the gold set without calling an LLM. This is what CI runs.

    make eval-sql-gold                      # guard + EXPLAIN + self-consistency
    uv run python scripts/eval_sql_gold.py --execute   # also run them for real

Six checks, and the point of all of them is that a broken gold set does not
report itself as a bad model. A reference query that stopped working after a
migration, or one that fails its own `required_columns`, shows up as a lower
accuracy number with no hint that the benchmark is the thing that broke.

Five of the six need no data at all, and the sixth (`EXPLAIN`) needs the
schema but not a single row - which is why CI can migrate an empty database
and still catch a renamed column. `--execute` adds the checks that do need
loaded data; those run locally, from tests/test_eval_gold_db.py.

This script is the only implementation of these assertions. The db test calls
`main()` rather than repeating them, so the two can never disagree.
"""

from __future__ import annotations

import argparse
import sys

import psycopg
import sqlglot
from sqlglot import exp

from football_ai.console import force_utf8
from football_ai.data import db
from football_ai.data.db import connect, readonly_dsn
from football_ai.evals.sql import coverage, execute, goldset, structure
from football_ai.sql_agent import generate, guard

# From the design doc. Changing these means changing what the benchmark
# measures, so a mismatch is an error rather than a warning.
EXPECTED_COUNTS = {
    "totals": 5,
    "rates": 6,
    "percentiles": 5,
    "transfers": 5,
    "teams": 5,
    "match_detail": 5,
    "filters": 5,
    "unanswerable": 4,
}


def _with_limit(sql: str, limit: int) -> str:
    tree = sqlglot.parse_one(sql, dialect=guard.DIALECT)
    return tree.limit(limit, copy=True).sql(dialect=guard.DIALECT)


def _order_column_indexes(sql: str) -> tuple[int, ...]:
    """Where every ORDER BY expression sits in the SELECT list.

    All of them, not just the first: `order by total_goals desc, date` is
    deterministic even when two rows share `total_goals`, and checking only
    the leading column would report a tie that does not exist.

    Raises when an ordering column is not projected, which makes "the ORDER BY
    columns must be in the SELECT list" an enforced rule rather than a
    convention. Without it the tie check cannot see the values it needs.
    """
    tree = sqlglot.parse_one(sql, dialect=guard.DIALECT)
    order = tree.args.get("order")
    if order is None:
        msg = "order_sensitive is true but the query has no ORDER BY"
        raise ValueError(msg)

    columns = [c.lower() for c in structure.output_columns(sql)]
    indexes: list[int] = []
    for ordered in order.expressions:
        target = ordered.this
        name = (
            target.alias_or_name
            if isinstance(target, (exp.Column, exp.Alias))
            else target.sql(dialect=guard.DIALECT)
        )
        if name.lower() not in columns:
            msg = f"ORDER BY {name!r} is not in the SELECT list ({', '.join(columns)})"
            raise ValueError(msg)
        indexes.append(columns.index(name.lower()))
    return tuple(indexes)


def check_guard(gold: goldset.GoldSet) -> list[str]:
    offenders = []
    for q in gold.questions:
        if not q.reference_sql:
            continue
        verdict = guard.validate(q.reference_sql)
        if not verdict.ok:
            offenders.append(f"{q.id}: guard refused it - {verdict.reason}")
    return offenders


def check_explain(gold: goldset.GoldSet, conn: psycopg.Connection) -> list[str]:
    offenders = []
    for q in gold.questions:
        if not q.reference_sql:
            continue
        outcome = execute.explain_sql(conn, q.reference_sql)
        if not outcome.ok:
            offenders.append(f"{q.id}: EXPLAIN failed - {outcome.error or outcome.guard_refusal}")
    return offenders


def check_few_shot_overlap(gold: goldset.GoldSet) -> list[str]:
    """A question the model was shown as an example measures its memory."""
    examples = {q.strip().lower() for q, _ in generate.FEW_SHOT}
    return [
        f"{q.id}: this question is also a FEW_SHOT example"
        for q in gold.questions
        if q.question.strip().lower() in examples
    ]


def check_category_counts(gold: goldset.GoldSet) -> list[str]:
    counts = {name: len(items) for name, items in gold.by_category().items()}
    offenders = []
    for name, expected in EXPECTED_COUNTS.items():
        actual = counts.get(name, 0)
        if actual != expected:
            offenders.append(f"category {name}: expected {expected} questions, found {actual}")
    for name in counts:
        if name not in EXPECTED_COUNTS:
            offenders.append(f"category {name}: not in the design's distribution")
    return offenders


def check_required_columns_exist(gold: goldset.GoldSet, conn: psycopg.Connection) -> list[str]:
    """Every `required_columns` name must be a real column of a relation the
    reference reads.

    The reference deliberately does NOT contain these columns: it holds the
    answer, while `required_columns` holds the output convention the prompt
    asks the model to follow. So "does the reference satisfy them" is the
    wrong question - but "is this a real column name" still catches the typo
    (`teams` vs `team`) that would fail every model forever.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = %s",
            (db.SCHEMA,),
        )
        catalog: dict[str, set[str]] = {}
        for relation, column in cur.fetchall():
            catalog.setdefault(relation.lower(), set()).add(column.lower())

    offenders = []
    for q in gold.questions:
        if not q.reference_sql or not q.required_columns:
            continue
        available: set[str] = set()
        for relation in structure.relations_used(q.reference_sql):
            available |= catalog.get(relation, set())
        unknown = [c for c in q.required_columns if c.lower() not in available]
        if unknown:
            offenders.append(
                f"{q.id}: required_columns names no such column on the relations the "
                f"reference reads: {', '.join(unknown)}"
            )
    return offenders


def check_self_consistency(gold: goldset.GoldSet) -> list[str]:
    """The reference must not violate the rules it holds the model to."""
    offenders = []
    for q in gold.questions:
        if not q.reference_sql:
            continue
        violated = structure.violated_forbidden(q.reference_sql, q.forbidden)
        if violated:
            offenders.append(
                f"{q.id}: the reference violates its own forbidden list: {', '.join(violated)}"
            )
        if q.order_sensitive:
            try:
                _order_column_indexes(q.reference_sql)
            except ValueError as exc:
                offenders.append(f"{q.id}: {exc}")
    return offenders


# --- data-dependent checks, only with --execute -----------------------------


def check_returns_rows(gold: goldset.GoldSet, conn: psycopg.Connection) -> list[str]:
    """An empty reference is a gold-set bug: the model would match it by
    returning nothing at all."""
    offenders = []
    for q in gold.questions:
        if not q.reference_sql:
            continue
        outcome = execute.run_sql(conn, q.reference_sql)
        if not outcome.ok:
            offenders.append(f"{q.id}: did not run - {outcome.error}")
        elif not outcome.rows:
            offenders.append(f"{q.id}: returned no rows")
    return offenders


def check_no_tie_at_the_cut(gold: goldset.GoldSet, conn: psycopg.Connection) -> list[str]:
    """With a tie on the last returned row two answers are both correct and
    the comparator cannot tell them apart."""
    offenders = []
    for q in gold.questions:
        if not q.order_sensitive or not q.reference_sql:
            continue
        columns = _order_column_indexes(q.reference_sql)
        rows = execute.run_sql(conn, q.reference_sql).rows
        if not rows:
            continue
        wider = execute.run_sql(conn, _with_limit(q.reference_sql, len(rows) + 1)).rows
        if len(wider) <= len(rows):
            continue
        last = tuple(rows[-1][i] for i in columns)
        extra = tuple(wider[-1][i] for i in columns)
        if last == extra:
            offenders.append(
                f"{q.id}: tie at the cut - row {len(rows)} and row {len(rows) + 1} share "
                f"the ordering key {last!r}"
            )
    return offenders


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="also run the references for real (needs loaded data)",
    )
    args = parser.parse_args(argv)

    gold = goldset.load()
    failures: list[str] = []
    failures += check_few_shot_overlap(gold)
    failures += check_category_counts(gold)
    failures += check_self_consistency(gold)
    failures += check_guard(gold)

    conn = connect(readonly_dsn())
    try:
        failures += check_explain(gold, conn)
        failures += check_required_columns_exist(gold, conn)
        if args.execute:
            failures += check_returns_rows(gold, conn)
            failures += check_no_tie_at_the_cut(gold, conn)
    finally:
        conn.close()

    references = sum(1 for q in gold.questions if q.reference_sql)
    if failures:
        print(f"{len(failures)} problem in the gold set:\n")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"{references}/{references} reference queries valid, {len(gold.questions)} questions")
    for name, items in gold.by_category().items():
        print(f"  {name:<14} {len(items)}")
    # Coverage is reported, never enforced: a gap is a growth direction, and
    # failing CI over one would reward breadth over the error-driven questions
    # that carry the signal.
    print()
    for line in coverage.summary(gold):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
