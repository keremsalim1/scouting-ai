"""Block until Postgres accepts connections, then exit.

A Python loop rather than a shell one so the Makefile needs no POSIX shell:
GNU make on Windows drives cmd.exe, where `for i in $(seq ...)` is a syntax
error. This also checks the thing we actually care about - that a client can
connect and query - rather than only the container's health flag.
"""

from __future__ import annotations

import argparse
import sys
import time

import psycopg

from football_ai.data.db import etl_dsn


def wait(timeout_s: float, interval_s: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout_s
    dsn = etl_dsn()
    attempt = 0
    last: Exception | None = None
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
                cur.execute("select 1")
            print(f"postgres ready after {attempt} attempt(s)")
            return True
        except psycopg.OperationalError as exc:
            last = exc
            time.sleep(interval_s)
    print(f"timed out after {timeout_s:.0f}s waiting for postgres: {last}", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for Postgres to accept connections.")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds (default 120)")
    args = parser.parse_args(argv)
    return 0 if wait(args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main())
