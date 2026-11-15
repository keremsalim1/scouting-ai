"""Ask a football question in natural language and run the resulting SQL.

    uv run python scripts/ask.py "Premier League'de en çok asist yapan 5 oyuncu"
    make ask Q="Serie A stoperleri arasinda pas isabeti en yuksek kim"

    uv run python scripts/ask.py --show-schema   # what the model is told
    uv run python scripts/ask.py --dry-run "..." # generate, do not execute

The query runs on the read-only connection, never the ETL one: the guard is
the first line of defence and the role is the one that holds (D-013).
"""

from __future__ import annotations

import argparse
import sys
import time

import psycopg

from football_ai.console import force_utf8
from football_ai.data.db import connect, etl_dsn, readonly_dsn
from football_ai.sql_agent import generate, guard


def _print_table(columns: list[str], rows: list[tuple], limit: int = 25) -> None:
    if not rows:
        print("  (no rows)")
        return
    widths = [len(c) for c in columns]
    shown = rows[:limit]
    for row in shown:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(_fmt(cell)))
    widths = [min(w, 34) for w in widths]

    header = "  " + "  ".join(c[:34].ljust(w) for c, w in zip(columns, widths, strict=True))
    print(header)
    print("  " + "  ".join("-" * w for w in widths))
    for row in shown:
        print(
            "  " + "  ".join(_fmt(cell)[:34].ljust(w) for cell, w in zip(row, widths, strict=True))
        )
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more row(s)")


def _fmt(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _hint(error: str, call_log: list[tuple[float, str]] | None = None) -> str:
    """Point at the actual cause.

    Two earlier versions of this sent the reader to the wrong place. The first
    blamed authentication for every failure, when the real one was a retired
    model name with a working key. The second read only the last error: a run
    that hit three 503s and then timed out was reported as "raise the
    timeout", when the pattern plainly said the model was saturated. So the
    whole sequence of calls is considered, not just how it ended.
    """
    lowered = error.lower()

    busy_calls = sum(
        1
        for _, outcome in (call_log or [])
        if outcome in {"ServiceUnavailableError", "RateLimitError", "Timeout"}
    )
    if busy_calls >= 2:
        return (
            f"{busy_calls} of the attempts failed with overload or timeout, so the\n"
            "model is saturated rather than misconfigured. The newest flash models\n"
            "are the most contended. Switch to a lighter one in .env:\n"
            "  LLM_MODEL=gemini/gemini-3.1-flash-lite\n"
            "Run `make llm-models` for the full list; -lite and gemma models\n"
            "usually have free capacity."
        )
    if "notfound" in lowered or "404" in lowered or "no longer available" in lowered:
        return (
            "The model name in LLM_MODEL does not exist for this key - this is not\n"
            "an auth problem. List what the key can reach:  make llm-models\n"
            "then put one of those in .env as LLM_MODEL=gemini/<name>."
        )
    if any(word in lowered for word in ("401", "403", "api key", "unauthenticated", "permission")):
        return (
            "The key was rejected. Put a valid GEMINI_API_KEY in .env\n"
            "(https://aistudio.google.com/apikey)."
        )
    if "temperature" in lowered and "support" in lowered:
        return (
            "The model rejected the temperature parameter. This is handled\n"
            "automatically - if you still see it, update litellm: uv sync --upgrade."
        )
    if any(word in lowered for word in ("503", "unavailable", "high demand", "overloaded")):
        return (
            "The model is busy, not misconfigured. Retries already happened and\n"
            "still hit it. Wait a minute, or switch LLM_MODEL to a less contended\n"
            "model (make llm-models; the -lite ones are usually freer)."
        )
    if any(word in lowered for word in ("429", "quota", "rate limit", "resource_exhausted")):
        return (
            "Rate limited or out of quota. Wait a minute, or switch LLM_MODEL to a\n"
            "model with a more generous free tier (make llm-models)."
        )
    if "timeout" in lowered:
        return "The provider timed out. Raise LLM_TIMEOUT_S in .env or try again."
    return "Run `make llm-models` to check the model name, and check the key in .env."


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="the question, in any language")
    parser.add_argument("--dry-run", action="store_true", help="generate SQL but do not run it")
    parser.add_argument("--show-schema", action="store_true", help="print the schema prompt")
    parser.add_argument("--max-rows", type=int, default=guard.DEFAULT_LIMIT)
    args = parser.parse_args(argv)

    if args.show_schema:
        with connect(etl_dsn()) as conn:
            print(generate.schema_text(conn))
        return 0

    question = " ".join(args.question).strip()
    if not question:
        parser.error("give a question, or use --show-schema")

    # Describing the schema needs the catalog; running the query must not have
    # write access. Two connections, two privilege levels.
    try:
        describe_conn = connect(etl_dsn())
        read_conn = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:
        print(f"cannot reach the database: {exc}", file=sys.stderr)
        print("start it with: make db-up", file=sys.stderr)
        return 2

    # Timed in three parts. When something is slow, the split says which part
    # to fix: describing the schema is local, generation is the provider, and
    # execution is Postgres.
    started = time.perf_counter()
    try:
        described = generate.schema_text(describe_conn)
        schema_s = time.perf_counter() - started
        print(
            f"schema prompt: {len(described):,} chars "
            f"(~{len(described) // 4:,} tokens) in {schema_s:.1f}s",
            file=sys.stderr,
        )

        generation_started = time.perf_counter()
        client = generate.LiteLLMClient()
        result = generate.text_to_sql(
            question, conn=describe_conn, client=client, max_rows=args.max_rows
        )
        rows = columns = None
        print(
            f"generation:    {time.perf_counter() - generation_started:.1f}s  model={client.model}",
            file=sys.stderr,
        )
        # A single total cannot tell "one slow answer" from "two refusals and a
        # retry", and those need opposite fixes. Break it down.
        for i, (seconds, outcome) in enumerate(client.call_log, start=1):
            print(f"  call {i}: {seconds:6.1f}s  {outcome}", file=sys.stderr)
        if client.retries_used:
            print(
                f"  {client.retries_used} retry(ies) after transient failures, plus backoff waits",
                file=sys.stderr,
            )
        if not client.temperature_supported:
            print(
                "  note: the model rejected temperature, so repeated runs may differ",
                file=sys.stderr,
            )
        if client.reasoning_effort and not client.reasoning_effort_supported:
            print("  note: the model rejected reasoning_effort", file=sys.stderr)

        if result.ok and result.sql and not args.dry_run:
            query_started = time.perf_counter()
            with read_conn.cursor() as cur:
                cur.execute(result.sql)
                rows = cur.fetchall()
                columns = [d.name for d in cur.description] if cur.description else []
            print(
                f"query:         {time.perf_counter() - query_started:.3f}s",
                file=sys.stderr,
            )
    finally:
        describe_conn.close()
        read_conn.close()

    print(f"\nQ: {question}\n")
    for i, attempt in enumerate(result.attempts, start=1):
        if attempt.refusal:
            print(f"attempt {i} refused: {attempt.refusal}")
            print(f"  {attempt.sql}\n")

    if not result.ok:
        print(f"FAILED: {result.error}", file=sys.stderr)
        print(_hint(result.error or "", client.call_log), file=sys.stderr)
        return 1

    print("SQL:")
    print(f"  {result.sql}\n")
    if result.repairs_used:
        print(f"(took {result.repairs_used} repair attempt)\n")

    if rows is not None and columns is not None:
        print(f"{len(rows)} row(s):")
        _print_table(columns, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
