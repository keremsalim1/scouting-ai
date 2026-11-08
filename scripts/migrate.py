"""Apply SQL migrations in order, once each.

Why plain SQL files and a ~60 line runner instead of Alembic: Alembic's value
is autogenerating diffs from SQLAlchemy models, and this project has no ORM
(day 5 validates SQL with sqlglot, not SQLAlchemy). Without models, Alembic
means hand-written SQL wrapped in Python migration scaffolding - all of the
ceremony, none of the benefit.

Why not docker-entrypoint-initdb.d: those scripts only run when the data
volume is empty, so every schema change would mean destroying the database.

Usage:
    uv run python scripts/migrate.py            # apply pending migrations
    uv run python scripts/migrate.py --status   # list applied / pending
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql as pgsql

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, SCHEMA, connect, etl_dsn, load_env

MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def ensure_roles(conn: psycopg.Connection) -> None:
    """Create the read-only role and pin its statement timeout.

    This lives in Python rather than in a migration because it needs a
    password from the environment, which must never land in a committed file.
    The timeout is attached to the role, so it applies to every session that
    logs in as it; the agent cannot override it.
    """
    load_env()
    user = os.environ.get("POSTGRES_RO_USER", "football_ro")
    password = os.environ.get("POSTGRES_RO_PASSWORD")
    timeout_ms = os.environ.get("POSTGRES_RO_STATEMENT_TIMEOUT_MS", "5000")
    if not password:
        msg = "POSTGRES_RO_PASSWORD is not set; copy .env.example to .env"
        raise RuntimeError(msg)

    with conn.cursor() as cur:
        cur.execute("select 1 from pg_roles where rolname = %s", (user,))
        exists = cur.fetchone() is not None
        # CREATE/ALTER ROLE are utility statements: Postgres does not accept
        # bind parameters in them, so the password cannot be passed as %s.
        # sql.Literal does the quoting and escaping that string formatting
        # would get wrong, and sql.Identifier does the same for the role name.
        ident = pgsql.Identifier(user)
        verb = pgsql.SQL("alter" if exists else "create")
        cur.execute(
            pgsql.SQL("{} role {} with login password {}").format(
                verb, ident, pgsql.Literal(password)
            )
        )
        cur.execute(
            pgsql.SQL("alter role {} set statement_timeout = {}").format(
                ident, pgsql.Literal(timeout_ms)
            )
        )
        # Belt and braces: the role must not be able to create databases or
        # roles even if someone later grants it more than intended.
        cur.execute(pgsql.SQL("alter role {} nocreatedb nocreaterole nosuperuser").format(ident))
    conn.commit()
    print(f"role {user!r} ready (statement_timeout={timeout_ms}ms)")


def ensure_tracking_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(f"create schema if not exists {SCHEMA}")
        cur.execute(
            f"""
            create table if not exists {SCHEMA}.schema_migrations (
                version     text primary key,
                sha256      text not null,
                applied_at  timestamptz not null default now()
            )
            """
        )
    conn.commit()


def applied(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(f"select version, sha256 from {SCHEMA}.schema_migrations")
        return dict(cur.fetchall())


def apply_all(conn: psycopg.Connection) -> int:
    done = applied(conn)
    count = 0
    for path in migration_files():
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if path.name in done:
            if done[path.name] != digest:
                # An applied migration was edited. Silently re-running it would
                # give two machines different schemas from the same repo.
                print(
                    f"ERROR {path.name} already applied but its contents changed.\n"
                    f"      Add a new migration instead of editing this one, or\n"
                    f"      recreate the database: "
                    f"docker compose -f infra/docker-compose.yml down -v",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            print(f"skip  {path.name}")
            continue
        # One transaction per migration: a failure leaves no partial schema.
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                f"insert into {SCHEMA}.schema_migrations (version, sha256) values (%s, %s)",
                (path.name, digest),
            )
        print(f"apply {path.name}")
        count += 1
    return count


def status(conn: psycopg.Connection) -> None:
    done = applied(conn)
    for path in migration_files():
        mark = "applied" if path.name in done else "pending"
        print(f"{mark:>8}  {path.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply SQL migrations in order.")
    parser.add_argument("--status", action="store_true", help="list migrations and exit")
    args = parser.parse_args(argv)

    force_utf8()
    with connect(etl_dsn(), autocommit=False) as conn:
        ensure_tracking_table(conn)
        if args.status:
            status(conn)
            return 0
        ensure_roles(conn)
        n = apply_all(conn)
        print(f"{n} migration(s) applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
