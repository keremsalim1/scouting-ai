"""Run the 40-question text-to-SQL benchmark against one or more models.

    make eval-sql                       # the default model
    make eval-sql-both                  # strong + weak, with a disagreement table

    uv run python scripts/eval_sql.py --category rates
    uv run python scripts/eval_sql.py --only totals-01,rates-03
    uv run python scripts/eval_sql.py --models gemini/gemini-3.8-flash,gemini/gemini-3.1-flash-lite

This needs an LLM key and a loaded database, so it is a local command. CI runs
`make eval-sql-gold`, which validates the gold set with no provider at all.

The exit code is the threshold verdict: 0 when the first model met it, 1 when
it did not or when no accuracy could be computed, 2 when the question filter
selected nothing. Day 20's eval gate reads that code, so it is wired now
rather than wrapped later.

Only the FIRST model gates. The weak model is a diagnostic: where the two
disagree is where the prompt is ambiguous (D-025).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, connect, readonly_dsn
from football_ai.evals.sql import goldset, report
from football_ai.evals.sql.runner import QuestionResult, run_suite
from football_ai.sql_agent import guard
from football_ai.sql_agent.generate import DEFAULT_MODEL, LiteLLMClient

DEFAULT_OUT = REPO_ROOT / "reports" / "eval_sql"
LATEST_REPORT = REPO_ROOT / "reports" / "eval_sql_latest.md"
DEFAULT_THRESHOLD = 0.70
WEAK_MODEL = "gemini/gemini-3.1-flash-lite"


def _verdict(result: QuestionResult) -> str:
    if result.infra_error:
        return "INFRA"
    if result.reference_failed:
        return "GOLD?"
    if result.correct is None:
        return "ran" if result.executes else "FAIL"
    if not result.correct:
        return "WRONG"
    if not (result.required_columns and result.no_forbidden):
        return "ok*"
    return "ok"


def _progress(result: QuestionResult) -> None:
    """One line per question: a 40-question run takes minutes."""
    print(f"  {result.id:<16} {_verdict(result):<6} {result.seconds:5.1f}s  {result.reason[:70]}")
    sys.stdout.flush()


def _select(gold: goldset.GoldSet, args: argparse.Namespace) -> tuple[goldset.Question, ...] | None:
    """The questions to run, or None after printing why there are none.

    A filter that silently matched nothing would be reported as 0% accuracy,
    which reads as a model failure.
    """
    if args.only:
        ids = tuple(part.strip() for part in args.only.split(",") if part.strip())
        try:
            return gold.select(ids=ids)
        except KeyError as exc:
            print(f"no such question id: {exc}")
            return None
    if args.category:
        if args.category not in goldset.CATEGORIES:
            print(f"unknown category {args.category!r}; known: {', '.join(goldset.CATEGORIES)}")
            return None
        selected = gold.select(category=args.category)
        if not selected:
            print(f"no questions in category {args.category!r}")
            return None
        return selected
    return gold.select()


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help=f"one model (default {DEFAULT_MODEL})")
    parser.add_argument("--models", help="comma-separated; the first one gates the exit code")
    parser.add_argument("--category", help=f"one of: {', '.join(goldset.CATEGORIES)}")
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="report directory")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-rows", type=int, default=guard.DEFAULT_LIMIT)
    args = parser.parse_args(argv)

    if args.models:
        models = [part.strip() for part in args.models.split(",") if part.strip()]
    else:
        models = [args.model or DEFAULT_MODEL]

    gold = goldset.load()
    questions = _select(gold, args)
    if questions is None:
        return 2

    print(f"{len(questions)} soru, {len(models)} model: {', '.join(models)}")

    # One connection and one reference cache for the whole run: the reference
    # queries are the same for every model and the season is frozen data, so
    # running them once per model would double the database work for nothing.
    reference_cache: dict = {}
    suites = []
    conn = connect(readonly_dsn())
    try:
        for model in models:
            print(f"\n{model}")
            client = LiteLLMClient(model=model)
            suites.append(
                run_suite(
                    questions,
                    conn=conn,
                    client=client,
                    model=model,
                    on_result=_progress,
                    max_rows=args.max_rows,
                    reference_cache=reference_cache,
                )
            )
    finally:
        conn.close()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = suites[0].run_id
    json_path = out_dir / f"{run_id}.json"
    md_path = out_dir / f"{run_id}.md"
    json_path.write_text(report.to_json(suites), encoding="utf-8")
    markdown = report.to_markdown(suites, threshold=args.threshold)
    md_path.write_text(markdown, encoding="utf-8")
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(md_path, LATEST_REPORT)

    scores = report.score(suites[0].results)
    print(f"\n{json_path}\n{md_path}")
    if scores.accuracy is None:
        print("doğruluk hesaplanamadı: puanlanabilir soru yok")
        return 1
    print(
        f"doğruluk %{scores.accuracy * 100:.1f} "
        f"({scores.correct}/{scores.scored}), eşik %{args.threshold * 100:.0f}"
    )
    return 0 if scores.accuracy >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
