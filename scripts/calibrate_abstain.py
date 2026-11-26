"""Measure where the abstention thresholds belong.

    uv run python scripts/calibrate_abstain.py

For each mode, runs every question in evals/rag/abstain_calibration.yaml and
prints the relevance score it produced. The number that matters is the gap
between the lowest in-corpus score and the highest out-of-corpus one: a
threshold is only defensible if that gap is positive.

If the two distributions overlap, this prints the overlapping questions by
name instead of a midpoint. That is the honest output - "these cases are not
separable" - and inventing a cut that splits them anyway is exactly the
unmeasured threshold the design doc names as an anti-goal.

Also prints per-query latency, so the cross-encoder's cost is a number rather
than an adjective.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, connect, readonly_dsn
from football_ai.rag.config import load as load_config
from football_ai.rag.embeddings import Embedder
from football_ai.rag.rerank import Reranker
from football_ai.rag.retrieval import methodology_search

CALIBRATION_PATH = REPO_ROOT / "evals" / "rag" / "abstain_calibration.yaml"
MODES = ("dense", "hybrid", "hybrid_rerank")


@dataclass
class Measurement:
    question: str
    expected_topic: str | None
    top_topic: str | None
    score: float | None
    seconds: float


def _load_questions(path: Path) -> tuple[list[dict], list[dict]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw["in_corpus"], raw["out_of_corpus"]


def _measure(conn, question: str, mode: str, embed_fn, rerank_fn, cfg) -> Measurement:
    started = time.perf_counter()
    # Thresholds are what we are trying to find, so they must not filter the
    # measurement: 0.0 lets every query report its score instead of abstaining.
    result = methodology_search(
        conn,
        question,
        embed_fn=embed_fn,
        rerank_fn=rerank_fn,
        mode=mode,
        config=cfg,
    )
    elapsed = time.perf_counter() - started
    return Measurement(
        question=question,
        expected_topic=None,
        top_topic=result.passages[0].topic if result.passages else None,
        score=result.relevance_score,
        seconds=elapsed,
    )


def _report_mode(mode: str, inside: list[Measurement], outside: list[Measurement]) -> None:
    print(f"\n{'=' * 78}\nmode: {mode}\n{'=' * 78}")

    # The two columns answer different questions on purpose: `score` is the
    # abstention signal (the maximum over ALL candidates), while the topic is
    # the first passage ranking chose to return. In dense and hybrid mode
    # those can disagree, and reading them as one number is the coupling the
    # design doc rejects. Ranking quality is day 11's measurement, not this
    # script's - `expect_topic` is printed, never asserted.
    print("\nin corpus:")
    for m in inside:
        score = "none" if m.score is None else f"{m.score:.4f}"
        hit = "—" if m.top_topic is None else m.top_topic
        flag = "" if m.expected_topic in (None, m.top_topic) else f"  (expected {m.expected_topic})"
        print(f"  {score:>8}  {m.seconds:5.2f}s  {hit:<24}{flag}  {m.question}")

    print("\nout of corpus:")
    for m in outside:
        score = "none" if m.score is None else f"{m.score:.4f}"
        print(f"  {score:>8}  {m.seconds:5.2f}s  {m.question}")

    in_scores = [m.score for m in inside if m.score is not None]
    out_scores = [m.score for m in outside if m.score is not None]
    if not in_scores or not out_scores:
        print("\nno comparable scores in one of the two groups")
        return

    lowest_in, highest_out = min(in_scores), max(out_scores)
    mean_latency = sum(m.seconds for m in inside + outside) / len(inside + outside)
    print(f"\nlowest in-corpus   {lowest_in:.4f}")
    print(f"highest out-of-corpus {highest_out:.4f}")
    print(f"mean latency       {mean_latency:.2f}s")

    if lowest_in > highest_out:
        print(f"gap                {lowest_in - highest_out:.4f}")
        print(f"suggested threshold {(lowest_in + highest_out) / 2:.4f}  (midpoint)")
    else:
        print("gap                NEGATIVE - the distributions overlap")
        print("overlapping questions (no midpoint is defensible):")
        for m in inside:
            if m.score is not None and m.score <= highest_out:
                print(f"  in  {m.score:.4f}  {m.question}")
        for m in outside:
            if m.score is not None and m.score >= lowest_in:
                print(f"  out {m.score:.4f}  {m.question}")


def main() -> None:
    force_utf8()
    in_corpus, out_of_corpus = _load_questions(CALIBRATION_PATH)
    cfg = load_config()
    measuring_cfg = type(cfg)(
        **{
            **cfg.__dict__,
            "dense_abstain_threshold": 0.0,
            "rerank_abstain_threshold": 0.0,
        }
    )

    embed_fn = Embedder().embed
    rerank_fn = Reranker(model_name=cfg.rerank_model).score

    conn = connect(readonly_dsn())
    try:
        for mode in MODES:
            mode_rerank = rerank_fn if mode == "hybrid_rerank" else None
            inside = []
            for entry in in_corpus:
                measurement = _measure(
                    conn, entry["question"], mode, embed_fn, mode_rerank, measuring_cfg
                )
                measurement.expected_topic = entry.get("expect_topic")
                inside.append(measurement)
            outside = [
                _measure(conn, entry["question"], mode, embed_fn, mode_rerank, measuring_cfg)
                for entry in out_of_corpus
            ]
            _report_mode(mode, inside, outside)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
