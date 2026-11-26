"""Run one methodology_search query by hand and read the result.

    make kb-search Q="Yüzdelikler nasıl hesaplanıyor?" MODE=hybrid_rerank

This is a way to look at retrieval, not a measurement - scripts/calibrate_abstain.py
owns the numbers.

Connects as `football_ro`, the role day 13's agent will have. If retrieval ever
needs more than SELECT, the failure belongs here rather than in the agent.
"""

from __future__ import annotations

import argparse

from football_ai.console import force_utf8
from football_ai.data.db import connect, readonly_dsn
from football_ai.rag.config import VALID_MODES
from football_ai.rag.config import load as load_config
from football_ai.rag.embeddings import Embedder
from football_ai.rag.rerank import Reranker
from football_ai.rag.retrieval import methodology_search

_SNIPPET = 200


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    # nargs="+" so an unquoted question still works when the script is called
    # directly; the Makefile quotes, so it arrives as one argument.
    parser.add_argument("query", nargs="+", help="the question, quoted")
    parser.add_argument("--mode", default="hybrid_rerank", choices=sorted(VALID_MODES))
    parser.add_argument("--top-n", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    force_utf8()
    args = _parse_args()
    query = " ".join(args.query)

    cfg = load_config()
    if args.top_n is not None:
        import dataclasses

        cfg = dataclasses.replace(cfg, top_n=args.top_n)

    # Only the reranking mode constructs a Reranker: the other two modes must
    # not pay for a ~600 MB download to answer a question they never use it for.
    rerank_fn = None
    if args.mode == "hybrid_rerank":
        rerank_fn = Reranker(model_name=cfg.rerank_model).score

    conn = connect(readonly_dsn())
    try:
        result = methodology_search(
            conn,
            query,
            embed_fn=Embedder().embed,
            rerank_fn=rerank_fn,
            mode=args.mode,
            config=cfg,
        )
    finally:
        conn.close()

    print(f"query: {result.query}")
    print(f"mode:  {result.mode}")
    if result.relevance_signal:
        score = "none" if result.relevance_score is None else f"{result.relevance_score:.3f}"
        print(f"signal: {result.relevance_signal}={score} threshold={result.threshold:.3f}")

    if result.abstained:
        # Abstaining is a correct outcome, not a failure: exit 0.
        print(f"\n{result.abstain_reason}")
        return

    for position, passage in enumerate(result.passages, start=1):
        print(f"\n[{position}] {passage.title} — {passage.source}")
        scores = [f"topic={passage.topic}"]
        if passage.dense_rank is not None:
            scores.append(f"dense #{passage.dense_rank} ({passage.dense_similarity:.3f})")
        if passage.lexical_rank is not None:
            scores.append(f"lexical #{passage.lexical_rank} ({passage.lexical_score:.4f})")
        if passage.rrf_score is not None:
            scores.append(f"rrf={passage.rrf_score:.5f}")
        if passage.rerank_score is not None:
            scores.append(f"rerank={passage.rerank_score:.3f}")
        print("    " + " | ".join(scores))
        snippet = " ".join(passage.content.split())[:_SNIPPET]
        print(f"    {snippet}...")


if __name__ == "__main__":
    main()
