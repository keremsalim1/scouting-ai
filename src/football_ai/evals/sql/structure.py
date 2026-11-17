"""Structural checks on generated SQL, over the sqlglot tree.

Result-set equality answers "is the number right". It cannot answer two other
questions the benchmark needs:

* **Is the output usable?** A percentile without its comparison group size is
  a number nobody can interpret, and a list of player names without the club
  cannot be acted on. The prompt asks for both; `missing_required` checks the
  model obeyed.
* **Was the number reached the right way?** A question about season totals
  must not carry `minutes_played >= 900`: the total already accounts for
  playing time, and the filter hides a player who produced a lot in few
  minutes. With a cut that happens to fall above every filtered-out player,
  the rows come back identical and only the structure gives it away.

Everything here reads the tree, never the text. `"minutes_played >= 900"` as a
substring would match a comment, an alias, or an ORDER BY.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from football_ai.evals.sql import goldset
from football_ai.sql_agent import guard

# Comparison nodes that turn a column reference into a filter. `exp.In` is
# deliberately absent: `minutes_played in (900, 1800)` is not a threshold, and
# no question in the gold set needs it.
_COMPARISONS: tuple[type[exp.Expression], ...] = (
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.EQ,
    exp.NEQ,
    exp.Between,
)

MINUTES_COLUMN = "minutes_played"
MINUTES_FILTER = "minutes_filter"


def _parse(sql: str) -> exp.Expression | None:
    """Parse, or return None - an unparsable query has no structure to check.

    The guard refuses unparsable SQL anyway, so reaching here means the caller
    wants a structural answer about something the guard already rejected. An
    empty answer is right; raising would make the report crash on a question
    the model simply failed.
    """
    try:
        return sqlglot.parse_one(sql, dialect=guard.DIALECT)
    except sqlglot.ParseError:
        return None


def _outermost_select(tree: exp.Expression) -> exp.Select | None:
    """The SELECT whose projections are the query's output columns.

    For a set operation the left-hand side names the result columns, which is
    what Postgres does too.
    """
    if isinstance(tree, exp.Select):
        return tree
    if isinstance(tree, exp.Subquery):
        inner = tree.this
        return _outermost_select(inner) if inner is not None else None
    if isinstance(tree, (exp.Union, exp.Intersect, exp.Except)):
        left = tree.left
        return _outermost_select(left) if left is not None else None
    return None


def output_columns(sql: str) -> tuple[str, ...]:
    """Projected names of the outermost SELECT: the alias, else the column."""
    tree = _parse(sql)
    if tree is None:
        return ()
    select = _outermost_select(tree)
    if select is None:
        return ()

    names: list[str] = []
    for projection in select.selects:
        if isinstance(projection, exp.Star):
            names.append("*")
            continue
        alias = projection.alias_or_name
        names.append(alias if alias else projection.sql(dialect=guard.DIALECT))
    return tuple(names)


def relations_used(sql: str) -> frozenset[str]:
    """Relation names the query reads, lowercased, without CTEs or schemas."""
    tree = _parse(sql)
    if tree is None:
        return frozenset()
    known = guard.cte_names(tree)
    found = {
        (table.name or "").lower()
        for table in tree.find_all(exp.Table)
        if (table.name or "").lower() not in known
    }
    return frozenset(name for name in found if name)


def has_minutes_filter(sql: str) -> bool:
    """Is `minutes_played` compared against something anywhere in the query?

    Walks up from each column reference rather than down from the WHERE clause,
    so a filter inside a subquery, a HAVING on `sum(minutes_played)`, or a
    reversed `900 <= minutes_played` all count. A bare projection or an
    ORDER BY does not.
    """
    tree = _parse(sql)
    if tree is None:
        return False
    for column in tree.find_all(exp.Column):
        if (column.name or "").lower() != MINUTES_COLUMN:
            continue
        node: exp.Expression | None = column
        while node is not None:
            if isinstance(node, _COMPARISONS):
                return True
            node = node.parent
    return False


def order_columns(sql: str) -> tuple[int, ...]:
    """Where each ORDER BY expression sits in the SELECT list.

    All of them: `order by total_goals desc, date` is deterministic even when
    two rows share `total_goals`, and the gold-set tie check needs the whole
    key to avoid reporting a tie that does not exist.

    Raises when an ordering column is not projected, which makes "the ORDER BY
    columns must be in the SELECT list" an enforced gold-set rule rather than
    a convention.
    """
    tree = _parse(sql)
    if tree is None:
        return ()
    order = tree.args.get("order")
    if order is None:
        return ()

    columns = [c.lower() for c in output_columns(sql)]
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


def ranking_keys(sql: str) -> tuple[int, ...]:
    """The column a ranking is genuinely ordered by: the LEADING ORDER BY key.

    Deliberately only the first. A trailing `, date, home_team` is the gold
    set author's tiebreak - it keeps the reference deterministic, but it is
    not what the question asked for, so it must not decide a verdict. Rows
    tied on the leading key are interchangeable.
    """
    found = order_columns(sql)
    return found[:1]


def missing_required(sql: str, required: tuple[str, ...]) -> tuple[str, ...]:
    """Which required output columns the query does not project.

    `select *` satisfies everything: the columns are there, the model just did
    not name them, and failing it would reward verbosity over correctness.
    """
    if not required:
        return ()
    produced = output_columns(sql)
    if "*" in produced:
        return ()
    have = {name.lower() for name in produced}
    return tuple(name for name in required if name.lower() not in have)


def violated_forbidden(sql: str, forbidden: tuple[str, ...]) -> tuple[str, ...]:
    """Which forbidden structures the query contains, in the given order."""
    unknown = [name for name in forbidden if name not in goldset.FORBIDDEN_CHECKS]
    if unknown:
        msg = (
            f"unknown forbidden check(s) {', '.join(repr(u) for u in unknown)}; "
            f"known: {', '.join(goldset.FORBIDDEN_CHECKS)}"
        )
        raise ValueError(msg)

    relations = relations_used(sql)
    violations: list[str] = []
    for check in forbidden:
        if check == MINUTES_FILTER:
            if has_minutes_filter(sql):
                violations.append(check)
        elif check in relations:
            violations.append(check)
    return tuple(violations)
