"""`methodology_search()`: find the kb/ passages that answer a question.

This tool retrieves and cites; it does not write an answer. Composing prose
from the passages is the agent's job (day 13). Three reasons, from the design
doc: the project rule is that the LLM interprets what a tool produced rather
than producing it; a second LLM layer here would summarize a summary and
compound its errors; and a tool that returns passages can be scored for
recall@5 for free, while a tool that returns a paragraph needs a judge.

The pipeline, truncated by `mode` so day 11 can ablate it:

    query
      |-- dense:    embed -> ORDER BY embedding <=> q   -> ranked list A
      '-- lexical:  websearch_to_tsquery -> ts_rank     -> ranked list B
                         |
                    RRF(A, B, k) -> fused candidates
                         |
                    rerank(query, candidates[:rerank_candidates])
                         |
                    abstention check on an ABSOLUTE signal
                         |
                    MethodologySearchResult (top_n passages, or none)

`dense` stops after list A, `hybrid` after RRF, `hybrid_rerank` runs it all.

The subtle part is abstention. A vector search always returns its nearest
neighbours - "nothing here is close" is not an answer ANN search can give -
so asked about a transfer fee it will hand back five passages about
possession adjustment, and an agent will build a sentence out of them. That
is where fabrication starts, so the refusal happens here, below the LLM.

Two things that must not be used for it:

  * An RRF score. It is a function of ranks only: the top hit of a nonsense
    query scores the same 1/(k+1) + 1/(k+1) as a perfect match.
  * The returned top_n. "Does the corpus cover this question" is a property
    of the query against the corpus, not of which rows ranking selected -
    and fusion can push the strongest dense hit out of the top five, which
    would make `hybrid` abstain on a question `dense` answers and leave day
    11 measuring ranking quality and abstention coupling as one number.

So the signal is the maximum over the *full* candidate list: cosine
similarity for `dense` and `hybrid`, the cross-encoder score for
`hybrid_rerank`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import psycopg
from pydantic import BaseModel

from football_ai.rag.config import VALID_MODES, RagConfig
from football_ai.rag.config import load as load_config
from football_ai.rag.fusion import FusedHit, fuse
from football_ai.rag.search import (
    Hit,
    assert_text_search_config,
    dense_search,
    lexical_search,
)

ABSTAIN_MESSAGE = "Bilgi tabanında bu konuda bilgi yok."

_LEXICAL_MODES = frozenset({"hybrid", "hybrid_rerank"})

EmbedFn = Callable[[list[str]], np.ndarray]
RerankFn = Callable[[str, list[str]], np.ndarray]


class Passage(BaseModel):
    """One cited chunk, with the provenance of why it was returned.

    `source` and `title` are never empty: both are `not null` in
    football.kb_chunks, so citation is a schema guarantee. The score fields
    are populated per mode - a consumer can tell which retriever found a
    passage, and at what rank, the same way day 8's `metric_keys` lets a
    scouting report say where a number came from.
    """

    doc_id: str
    chunk_index: int
    topic: str
    source: str
    title: str
    content: str
    dense_rank: int | None = None
    dense_similarity: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class MethodologySearchResult(BaseModel):
    query: str
    mode: str
    passages: list[Passage]
    abstained: bool
    abstain_reason: str | None = None
    relevance_signal: str | None = None
    relevance_score: float | None = None
    threshold: float | None = None
    generated_at: datetime


def _passage(candidate: FusedHit, rerank_score: float | None = None) -> Passage:
    return Passage(
        doc_id=candidate.hit.doc_id,
        chunk_index=candidate.hit.chunk_index,
        topic=candidate.hit.topic,
        source=candidate.hit.source,
        title=candidate.hit.title,
        content=candidate.hit.content,
        dense_rank=candidate.dense_rank,
        dense_similarity=candidate.dense_similarity,
        lexical_rank=candidate.lexical_rank,
        lexical_score=candidate.lexical_score,
        rrf_score=candidate.rrf_score,
        rerank_score=rerank_score,
    )


def _as_candidates(hits: list[Hit]) -> list[FusedHit]:
    """Wrap dense-only hits so all three modes share one downstream path.

    `rrf_score` stays None: nothing was fused, and reporting a fusion score
    for a mode that did not fuse would be a lie in the provenance.
    """
    return [
        FusedHit(
            hit=hit,
            rrf_score=None,
            dense_rank=hit.rank,
            dense_similarity=hit.score,
            lexical_rank=None,
            lexical_score=None,
        )
        for hit in hits
    ]


def _abstained(
    query: str,
    mode: str,
    signal: str,
    score: float | None,
    threshold: float,
) -> MethodologySearchResult:
    if score is None:
        detail = f"{signal} yok (hiç aday bulunamadı)"
    else:
        detail = f"{signal} {score:.3f} < eşik {threshold:.3f}"
    return MethodologySearchResult(
        query=query,
        mode=mode,
        passages=[],
        abstained=True,
        abstain_reason=f"{ABSTAIN_MESSAGE} ({detail})",
        relevance_signal=signal,
        relevance_score=score,
        threshold=threshold,
        generated_at=datetime.now(UTC),
    )


def methodology_search(
    conn: psycopg.Connection,
    query: str,
    *,
    embed_fn: EmbedFn,
    rerank_fn: RerankFn | None = None,
    mode: str = "hybrid_rerank",
    config: RagConfig | None = None,
) -> MethodologySearchResult:
    if mode not in VALID_MODES:
        msg = f"unknown mode {mode!r}; expected one of {sorted(VALID_MODES)}"
        raise ValueError(msg)
    if mode == "hybrid_rerank" and rerank_fn is None:
        msg = "mode 'hybrid_rerank' needs a rerank_fn"
        raise ValueError(msg)

    cfg = config or load_config()

    # Before embedding or connecting: a blank query has no answer, and paying
    # for a model call to discover that is waste.
    if not query.strip():
        return MethodologySearchResult(
            query=query,
            mode=mode,
            passages=[],
            abstained=True,
            abstain_reason=f"{ABSTAIN_MESSAGE} (boş sorgu)",
            generated_at=datetime.now(UTC),
        )

    if mode in _LEXICAL_MODES:
        assert_text_search_config(conn, cfg.text_search_config)

    dense_hits = dense_search(conn, embed_fn([query])[0], limit=cfg.dense_candidates)

    if mode == "dense":
        candidates = _as_candidates(dense_hits)
    else:
        lexical_hits = lexical_search(
            conn,
            query,
            limit=cfg.lexical_candidates,
            text_search_config=cfg.text_search_config,
        )
        candidates = fuse(dense_hits, lexical_hits, k=cfg.rrf_k)

    if mode != "hybrid_rerank":
        # Signal over every dense hit, not over the returned top_n - see the
        # module docstring.
        best_dense = max((hit.score for hit in dense_hits), default=None)
        if best_dense is None or best_dense < cfg.dense_abstain_threshold:
            return _abstained(
                query, mode, "dense_similarity", best_dense, cfg.dense_abstain_threshold
            )
        return MethodologySearchResult(
            query=query,
            mode=mode,
            passages=[_passage(c) for c in candidates[: cfg.top_n]],
            abstained=False,
            relevance_signal="dense_similarity",
            relevance_score=best_dense,
            threshold=cfg.dense_abstain_threshold,
            generated_at=datetime.now(UTC),
        )

    assert rerank_fn is not None  # guarded above; narrows the type
    # Sliced before the cross-encoder because fusion can surface up to
    # dense_candidates + lexical_candidates rows, and this is the one stage
    # whose cost scales with that number.
    shortlist = candidates[: cfg.rerank_candidates]
    scores = rerank_fn(query, [c.hit.content for c in shortlist])
    reranked = sorted(
        zip(shortlist, (float(s) for s in scores), strict=True),
        key=lambda pair: (-pair[1], pair[0].hit.chunk_id),
    )

    best_rerank = max((score for _, score in reranked), default=None)
    if best_rerank is None or best_rerank < cfg.rerank_abstain_threshold:
        return _abstained(query, mode, "rerank_score", best_rerank, cfg.rerank_abstain_threshold)
    return MethodologySearchResult(
        query=query,
        mode=mode,
        passages=[
            _passage(candidate, rerank_score=score) for candidate, score in reranked[: cfg.top_n]
        ],
        abstained=False,
        relevance_signal="rerank_score",
        relevance_score=best_rerank,
        threshold=cfg.rerank_abstain_threshold,
        generated_at=datetime.now(UTC),
    )
