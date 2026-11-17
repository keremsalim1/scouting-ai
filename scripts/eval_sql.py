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
    if args.smoke:
        if args.category or args.only:
            print("--smoke picks the questions itself; drop --category/--only")
            return None
        # One question per category: enough to notice a prompt change broke a
        # whole category, small enough to run inside one day of free-tier
        # quota (20 requests), which the full suite is not.
        return tuple(items[0] for items in gold.by_category().values())
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


def _write_report(out_dir: Path, name: str, suites: list, threshold: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{name}.json"
    md_path = out_dir / f"{name}.md"
    # Trailing newline so the end-of-file-fixer hook does not rewrite every
    # report the moment it is committed.
    json_path.write_text(report.to_json(suites) + "\n", encoding="utf-8")
    md_path.write_text(report.to_markdown(suites, threshold=threshold), encoding="utf-8")
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(md_path, LATEST_REPORT)
    print(f"\n{json_path}\n{md_path}")
    return json_path


def _verdict_code(suite, threshold: float) -> int:
    scores = report.score(suite.results)
    if scores.accuracy is None:
        print("doğruluk hesaplanamadı: puanlanabilir soru yok")
        return 1
    print(
        f"doğruluk %{scores.accuracy * 100:.1f} "
        f"({scores.correct}/{scores.scored}), eşik %{threshold * 100:.0f}"
    )
    return 0 if scores.accuracy >= threshold else 1


def _merge_runs(args: argparse.Namespace) -> int:
    """Stitch earlier partial runs into one report, with no provider call.

    This exists because the free tier allows 20 requests a day while the gold
    set has 40 questions: the suite is run in batches with `--category` or
    `--only` and the batches are only useful if they combine into a single
    accuracy number.
    """
    source = Path(args.merge)
    files = sorted(source.glob("*.json")) if source.is_dir() else []
    files = [f for f in files if not f.name.endswith("-merged.json")]
    if not files:
        print(f"no run files to merge in {source}")
        return 2

    loaded = [s for f in files for s in report.from_json(f.read_text(encoding="utf-8"))]
    wanted = args.model or args.models
    if wanted:
        loaded = [s for s in loaded if s.model == wanted]
    models = sorted({s.model for s in loaded})
    if not loaded:
        print(f"no runs for model {wanted!r} in {source}")
        return 2
    if len(models) > 1:
        print(f"several models present; pass --model to pick one: {', '.join(models)}")
        return 2

    merged = report.merge(loaded)
    print(
        f"{len(files)} dosyadan {len(merged.results)} soru birleştirildi "
        f"({merged.model}, {len(loaded)} koşu)"
    )
    _write_report(Path(args.out), f"{merged.run_id}-merged", [merged], args.threshold)
    return _verdict_code(merged, args.threshold)


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help=f"one model (default {DEFAULT_MODEL})")
    parser.add_argument("--models", help="comma-separated; the first one gates the exit code")
    parser.add_argument("--category", help=f"one of: {', '.join(goldset.CATEGORIES)}")
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="one question per category: a quick regression check inside one day's quota",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="report directory")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-rows", type=int, default=guard.DEFAULT_LIMIT)
    parser.add_argument(
        "--merge",
        metavar="DIR",
        help="stitch earlier runs in DIR into one report; makes no provider call",
    )
    args = parser.parse_args(argv)

    if args.merge:
        return _merge_runs(args)

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

    _write_report(Path(args.out), suites[0].run_id, suites, args.threshold)
    return _verdict_code(suites[0], args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())
