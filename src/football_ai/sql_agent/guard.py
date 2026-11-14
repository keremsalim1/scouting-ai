"""Validate LLM-generated SQL before it reaches the database.

This is defence in depth, not the defence. The actual guarantee is the
`football_ro` role, which holds no INSERT, UPDATE, DELETE, CREATE or DROP
privilege and carries a server-side `statement_timeout` (D-013). A parser can
in principle be out-argued; a role that lacks the privilege cannot. This layer
exists to fail fast, to give the model a readable reason it can repair from,
and to stop expensive-but-legal queries.

The rules, and why each one is here:

* **Parse or reject.** If sqlglot cannot parse it, we do not run it. Anything
  it falls back to parsing as a bare `Command` is by definition syntax we do
  not understand, which is exactly when refusing is right.
* **Exactly one statement.** `select 1; drop table players` parses as two.
* **Walk the whole tree, not just the root.** Postgres allows data-modifying
  CTEs, and `with d as (delete from players returning *) select * from d`
  parses with a `Select` at the root. Checking the root type alone would wave
  it through.
* **Relations must be on the allowlist.** CTE names are excluded, otherwise
  legitimate `with` queries would be rejected for referencing themselves.
* **Unknown functions are refused.** sqlglot models every standard SQL
  function this project needs as a typed node; a function that arrives as
  `Anonymous` is one it does not know. Refusing that class is a structural
  allowlist, so `pg_sleep`, `pg_read_file`, `lo_import`, `dblink` and anything
  else nobody thought of are all covered. A denylist only blocks what its
  author remembered.
* **A LIMIT is always present.** Added when missing, clamped when too large,
  so a careless query cannot stream a million pass rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from football_ai.data.db import ALLOWED_FUNCTIONS, ALLOWED_RELATIONS, SCHEMA

DIALECT = "postgres"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000

# A bare table name is fine: `search_path` points at the football schema.
ALLOWED_SCHEMAS: frozenset[str] = frozenset({SCHEMA, ""})

# Set operations are legitimate query shapes, so they may sit at the root.
ALLOWED_ROOTS: tuple[type[exp.Expression], ...] = (
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
    exp.Subquery,
)

# Any of these anywhere in the tree is a refusal, including inside a CTE.
# exp.Command is sqlglot's "I could not parse this" fallback.
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Copy,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Command,
)

_NODE_LABELS = {
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
    exp.Merge: "MERGE",
    exp.Drop: "DROP",
    exp.Create: "CREATE",
    exp.Alter: "ALTER",
    exp.TruncateTable: "TRUNCATE",
    exp.Grant: "GRANT",
    exp.Copy: "COPY",
    exp.Set: "SET",
    exp.Transaction: "BEGIN/START TRANSACTION",
    exp.Commit: "COMMIT",
    exp.Rollback: "ROLLBACK",
    exp.Command: "an unrecognised command",
}


class GuardError(Exception):
    """Raised by `validate(..., raising=True)` when SQL is refused."""


@dataclass(frozen=True)
class GuardResult:
    """Outcome of validation.

    `sql` is the rewritten statement that is safe to execute - it may differ
    from the input because a LIMIT was added or clamped. `reason` is written
    for the model to read: the repair attempt feeds it straight back.
    """

    ok: bool
    sql: str | None = None
    reason: str | None = None
    limit_applied: int | None = None

    def __bool__(self) -> bool:
        return self.ok


def _refuse(reason: str) -> GuardResult:
    return GuardResult(ok=False, reason=reason)


def _cte_names(tree: exp.Expression) -> set[str]:
    """Names introduced by WITH, which may be referenced like tables."""
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            names.add(alias.lower())
    return names


def _relation_name(table: exp.Table) -> tuple[str, str]:
    schema = (table.text("db") or "").lower()
    name = (table.name or "").lower()
    return schema, name


def _check_relations(tree: exp.Expression) -> str | None:
    known = _cte_names(tree)
    for table in tree.find_all(exp.Table):
        schema, name = _relation_name(table)
        if not name:
            return "a table expression could not be resolved to a name"
        if name in known and not schema:
            continue
        if schema not in ALLOWED_SCHEMAS:
            return (
                f"schema {schema!r} is not readable; only the {SCHEMA!r} schema is, "
                f"and these relations: {', '.join(ALLOWED_RELATIONS)}"
            )
        if name not in ALLOWED_RELATIONS:
            return (
                f"relation {name!r} is not on the allowlist; "
                f"readable relations are: {', '.join(ALLOWED_RELATIONS)}"
            )
    return None


def _check_functions(tree: exp.Expression) -> str | None:
    for node in tree.find_all(exp.Anonymous):
        name = (node.name or "").lower()
        if name not in ALLOWED_FUNCTIONS:
            return (
                f"function {name!r} is not permitted; use standard SQL functions "
                f"(aggregates, window functions, cast, coalesce, nullif)"
            )
    return None


def _check_forbidden(tree: exp.Expression) -> str | None:
    for node_type in FORBIDDEN_NODES:
        if isinstance(tree, node_type) or next(tree.find_all(node_type), None) is not None:
            label = _NODE_LABELS.get(node_type, node_type.__name__.upper())
            return f"{label} is not allowed; only read-only SELECT queries are"
    return None


def _apply_limit(tree: exp.Expression, max_rows: int) -> tuple[exp.Expression, int]:
    """Ensure a LIMIT no larger than `max_rows`. Returns the effective limit."""
    existing = tree.args.get("limit")
    if existing is not None:
        value = existing.expression
        if isinstance(value, exp.Literal) and value.is_int:
            current = int(value.name)
            if 0 < current <= max_rows:
                return tree, current
    return tree.limit(max_rows, copy=False), max_rows


def validate(
    sql: str,
    *,
    max_rows: int = DEFAULT_LIMIT,
    raising: bool = False,
) -> GuardResult:
    """Check `sql` and return a safe rewrite, or a refusal with a reason."""
    max_rows = min(max_rows, MAX_LIMIT)

    def done(result: GuardResult) -> GuardResult:
        if raising and not result.ok:
            raise GuardError(result.reason)
        return result

    if not sql or not sql.strip():
        return done(_refuse("the query is empty; produce a single SELECT statement"))

    try:
        statements = sqlglot.parse(sql, dialect=DIALECT)
    except sqlglot.ParseError as exc:
        return done(_refuse(f"the query is not valid SQL: {exc}"))

    statements = [s for s in statements if s is not None]
    if not statements:
        return done(_refuse("the query is empty; produce a single SELECT statement"))
    if len(statements) > 1:
        return done(
            _refuse(
                f"{len(statements)} statements were given; submit exactly one SELECT "
                f"with no semicolon-separated extras"
            )
        )

    tree = statements[0]

    if not isinstance(tree, ALLOWED_ROOTS):
        label = _NODE_LABELS.get(type(tree), type(tree).__name__.upper())
        return done(_refuse(f"{label} is not allowed; only read-only SELECT queries are"))

    # Functions are checked before relations on purpose. `dblink(...)` in a
    # FROM clause parses as a Table whose name will not resolve, and "a table
    # expression could not be resolved" tells the repair attempt nothing;
    # "function 'dblink' is not permitted" tells it exactly what to drop.
    for check in (_check_forbidden, _check_functions, _check_relations):
        reason = check(tree)
        if reason:
            return done(_refuse(reason))

    tree, limit = _apply_limit(tree, max_rows)
    return GuardResult(ok=True, sql=tree.sql(dialect=DIALECT), limit_applied=limit)
