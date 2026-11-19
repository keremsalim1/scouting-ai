"""Database connection helpers.

Two roles, deliberately separate:
  * ``etl_dsn()``  — the owner. Writes. Used by migrations and the ETL.
  * ``readonly_dsn()`` — SELECT only, with a server-side statement timeout.
    From day 5 this is the only role the SQL agent ever sees.

Keeping them in separate functions means a module that only imports
``readonly_dsn`` cannot accidentally obtain write access.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "football"

# Base tables the SQL agent may reference. Kept here so the schema, the ETL
# and the allowlist cannot drift apart; a database test asserts they exist.
ALLOWED_TABLES: tuple[str, ...] = (
    "teams",
    "players",
    "matches",
    "lineups",
    "player_match_stats",
    "shots",
    "passes",
    "data_quality",
    "data_quality_features",
    "metric_definitions",
    "metric_config",
)

# Views the agent may reference. These are the grain scouting questions are
# actually asked at, so they are listed first in the generated prompt.
ALLOWED_VIEWS: tuple[str, ...] = (
    "player_metrics",
    "player_per90",
    "player_season",
    "player_season_club",
    "position_map",
)

# Everything the agent is allowed to read. `schema_migrations` is deliberately
# absent: it is operational metadata, not football data.
ALLOWED_RELATIONS: tuple[str, ...] = tuple(sorted({*ALLOWED_TABLES, *ALLOWED_VIEWS}))

# Functions declared in migration 002. sqlglot models every standard SQL
# function we need as a typed node, so these are the only ones that arrive as
# "unknown" and still have to be permitted.
ALLOWED_FUNCTIONS: frozenset[str] = frozenset({"position_group", "position_group_broad"})


def load_env() -> None:
    """Load .env from the repo root. Real environment variables win."""
    load_dotenv(REPO_ROOT / ".env", override=False)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        msg = f"{name} is not set; copy .env.example to .env and fill it in"
        raise RuntimeError(msg)
    return value


def _dsn(user: str, password: str) -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "15432")
    db = os.environ.get("POSTGRES_DB", "football")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def etl_dsn() -> str:
    """Owner connection string: full write access."""
    load_env()
    return _dsn(_require("POSTGRES_USER"), _require("POSTGRES_PASSWORD"))


def readonly_dsn() -> str:
    """Read-only connection string, as used by the SQL agent."""
    load_env()
    return _dsn(_require("POSTGRES_RO_USER"), _require("POSTGRES_RO_PASSWORD"))


def connect(dsn: str | None = None, *, autocommit: bool = False) -> psycopg.Connection:
    """Open a connection with ``search_path`` already pointing at the schema.

    Setting search_path here means queries and COPY statements can use bare
    table names, and the day-5 validator does not have to rewrite identifiers.
    """
    conn = psycopg.connect(dsn or etl_dsn(), autocommit=autocommit)
    with conn.cursor() as cur:
        cur.execute(f"set search_path to {SCHEMA}, public")
    if not autocommit:
        conn.commit()
    return conn
