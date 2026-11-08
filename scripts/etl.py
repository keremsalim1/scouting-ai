"""Load OpenPlay 2025/26 into Postgres. Full reload, idempotent by design.

    uv run python scripts/etl.py                 # load everything
    uv run python scripts/etl.py --benchmark     # COPY vs to_sql, measured
    uv run python scripts/etl.py --counts        # print row counts and exit

The whole load runs in one transaction: TRUNCATE then COPY, commit at the end.
Running it twice therefore produces byte-identical tables and never
duplicates, which is the day 2 acceptance criterion.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings

import openplay as op
import pandas as pd

from football_ai.console import force_utf8
from football_ai.data import extract as ex
from football_ai.data import load as ld
from football_ai.data.db import REPO_ROOT, connect, etl_dsn

SEASON = "2025/26"
LEAGUES = ("eng", "esp", "ita")
REPORT_JSON = REPO_ROOT / "reports" / "data_validation_2526.json"


def read_source() -> dict[str, pd.DataFrame]:
    """Pull every league from OpenPlay and concatenate into one frame per table.

    Concatenating here (rather than loading league by league) means the
    dimension filter sees every referenced id at once, so teams/players are
    loaded exactly once and no foreign key can dangle.
    """
    parts: dict[str, list[pd.DataFrame]] = {
        "matches": [],
        "lineups": [],
        "player_match_stats": [],
        "shots": [],
        "passes": [],
    }
    for comp in LEAGUES:
        t0 = time.perf_counter()
        parts["matches"].append(ex.extract_matches(op.matches(comp, SEASON)))
        parts["lineups"].append(ex.extract_lineups(op.lineups(comp, SEASON)))
        parts["player_match_stats"].append(
            ex.extract_player_match_stats(op.player_match_stats(comp, SEASON))
        )
        parts["shots"].append(ex.extract_shots(op.shots(comp, SEASON)))
        events = op.events(
            comp,
            SEASON,
            columns=[
                "match_id",
                "event_id",
                "event_id_sub",
                "comp",
                "season",
                "team_id",
                "player_id",
                "type",
                "period",
                "minute",
                "second",
                "expanded_minute",
                "x",
                "y",
                "end_x",
                "end_y",
                "outcome",
                *ex.PASS_QUALIFIER_RENAMES,
            ],
        )
        parts["passes"].append(ex.extract_passes(events))
        print(f"  read {comp} in {time.perf_counter() - t0:5.1f}s")

    frames = {name: pd.concat(chunks, ignore_index=True) for name, chunks in parts.items()}

    facts = list(frames.values())
    frames["teams"] = ex.extract_teams(op.teams(), ex.referenced_team_ids(facts))
    frames["players"] = ex.extract_players(op.players(), ex.referenced_player_ids(facts))
    return frames


def read_data_quality() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not REPORT_JSON.exists():
        print(f"  no {REPORT_JSON.name}; run `make validate` first", file=sys.stderr)
        return None
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    return ex.extract_data_quality(report, data_tag=op.DATA_TAG)


def run_load() -> dict[str, int]:
    print("reading OpenPlay...")
    t0 = time.perf_counter()
    frames = read_source()
    dq = read_data_quality()
    print(f"read complete in {time.perf_counter() - t0:.1f}s")
    for name in (*ex.LOAD_ORDER, *(["data_quality"] if dq is not None else [])):
        if name in frames:
            print(f"  {name:<20} {len(frames[name]):>9,} rows")

    dq_tables = ["data_quality", "data_quality_features"]
    all_tables = [*ex.LOAD_ORDER, *dq_tables]

    loaded: dict[str, int] = {}
    with connect(etl_dsn()) as conn:
        t0 = time.perf_counter()
        # Single transaction: TRUNCATE is transactional in Postgres, so a
        # failure anywhere below leaves the previous contents intact.
        with conn.transaction():
            # Only the frozen fact tables are reloaded. data_quality is
            # append-only history and is deliberately left alone here.
            ld.truncate(conn, ex.LOAD_ORDER)
            for name in ex.LOAD_ORDER:
                t = time.perf_counter()
                loaded[name] = ld.copy_dataframe(conn, name, frames[name])
                dt = time.perf_counter() - t
                rate = loaded[name] / dt if dt > 0 else 0
                print(
                    f"  COPY {name:<20} {loaded[name]:>9,} rows  {dt:6.2f}s  {rate:>9,.0f} rows/s"
                )
            if dq is not None:
                metrics, features = dq
                loaded["data_quality"] = ld.insert_ignoring_conflicts(conn, "data_quality", metrics)
                loaded["data_quality_features"] = ld.insert_ignoring_conflicts(
                    conn, "data_quality_features", features
                )
                print(
                    f"  APPEND data_quality        {loaded['data_quality']:>6,} new rows "
                    f"(report generated_at is the key)"
                )
        total = time.perf_counter() - t0
        print(f"load committed in {total:.1f}s")
        ld.analyze(conn, all_tables)
        print("analyze done")
    return loaded


def benchmark(rows: int = 50_000) -> None:
    """Measure COPY against pandas.to_sql on the same slice of pass rows.

    to_sql needs SQLAlchemy; if it is absent we only report COPY and say so,
    rather than guessing at a number.
    """
    warnings.simplefilter("ignore", op.CoverageWarning)
    events = op.events(
        "eng",
        SEASON,
        columns=[
            "match_id",
            "event_id",
            "event_id_sub",
            "comp",
            "season",
            "team_id",
            "player_id",
            "type",
            "period",
            "minute",
            "second",
            "expanded_minute",
            "x",
            "y",
            "end_x",
            "end_y",
            "outcome",
            *ex.PASS_QUALIFIER_RENAMES,
        ],
    )
    frame = ex.extract_passes(events).head(rows)
    print(f"benchmark on {len(frame):,} pass rows")

    with connect(etl_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("create temp table bench_copy (like football.passes)")
        conn.commit()
        t0 = time.perf_counter()
        with (
            conn.cursor() as cur,
            cur.copy("copy bench_copy ({}) from stdin".format(", ".join(ex.PASS_COLUMNS))) as cp,
        ):
            for row in frame.loc[:, list(ex.PASS_COLUMNS)].itertuples(index=False, name=None):
                cp.write_row(tuple(ld.to_copy_value(v) for v in row))
        copy_s = time.perf_counter() - t0
        conn.rollback()
        print(f"  COPY            {copy_s:7.2f}s  {len(frame) / copy_s:>10,.0f} rows/s")

    try:
        import sqlalchemy
    except ModuleNotFoundError:
        print("  to_sql          not measured (sqlalchemy not installed)")
        print("  install with: uv add --dev sqlalchemy  then re-run --benchmark")
        return

    engine = sqlalchemy.create_engine(etl_dsn())
    t0 = time.perf_counter()
    frame.to_sql("bench_to_sql", engine, schema="football", if_exists="replace", index=False)
    to_sql_s = time.perf_counter() - t0
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("drop table if exists football.bench_to_sql"))
    print(f"  to_sql          {to_sql_s:7.2f}s  {len(frame) / to_sql_s:>10,.0f} rows/s")
    print(f"  COPY is {to_sql_s / copy_s:.1f}x faster on this machine")


def print_counts() -> None:
    tables = [*ex.LOAD_ORDER, "data_quality", "data_quality_features"]
    with connect(etl_dsn()) as conn:
        for table, count in ld.row_counts(conn, tables).items():
            print(f"  {table:<22} {count:>9,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load OpenPlay 2025/26 into Postgres.")
    parser.add_argument("--benchmark", action="store_true", help="compare COPY with to_sql")
    parser.add_argument("--counts", action="store_true", help="print row counts and exit")
    parser.add_argument(
        "--rows", type=int, default=50_000, help="rows to use for --benchmark (default 50000)"
    )
    args = parser.parse_args(argv)

    force_utf8()
    warnings.simplefilter("ignore", op.CoverageWarning)
    if args.counts:
        print_counts()
        return 0
    if args.benchmark:
        benchmark(args.rows)
        return 0

    loaded = run_load()
    print("\nloaded:")
    for table, count in loaded.items():
        print(f"  {table:<22} {count:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
