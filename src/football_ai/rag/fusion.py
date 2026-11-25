"""Reciprocal rank fusion of the dense and lexical result lists.

`score = sum over lists of 1/(k + rank)`. The point of RRF is what it refuses
to look at: the two retrievers' scores are not comparable - cosine similarity
is bounded in [-1, 1], `ts_rank` is unbounded and length-dependent - and any
attempt to normalize them into a shared scale is a guess about distributions
nobody measured. Ranks are comparable without assuming anything.

`k` damps the top of each list: with k=60 the gap between rank 1 and rank 2 is
small, so a chunk both retrievers merely liked outranks one that a single
retriever loved. That is the behaviour hybrid search is for.

What RRF cannot do is tell you whether anything is relevant at all. A fused
score is a function of ranks only, so the top hit of a nonsense query scores
exactly what a perfect match scores. Abstention therefore reads an absolute
signal (cosine similarity or the reranker), never this number - see
retrieval.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from football_ai.rag.search import Hit


@dataclass(frozen=True)
class FusedHit:
    hit: Hit
    rrf_score: float
    dense_rank: int | None
    dense_similarity: float | None
    lexical_rank: int | None
    lexical_score: float | None


def fuse(dense: Sequence[Hit], lexical: Sequence[Hit], *, k: int) -> list[FusedHit]:
    """Combine two ranked lists by rank, carrying each retriever's provenance.

    Takes the two lists as named arguments rather than a generic sequence of
    lists because the provenance fields are how a consumer answers "why was
    this passage returned", and a generic fuser has no way to label them.

    Returns every candidate, unsliced: depth belongs to the caller.
    """
    by_chunk: dict[int, dict[str, object]] = {}

    for hit in dense:
        by_chunk.setdefault(hit.chunk_id, {"hit": hit})
        by_chunk[hit.chunk_id]["dense"] = hit
    for hit in lexical:
        by_chunk.setdefault(hit.chunk_id, {"hit": hit})
        by_chunk[hit.chunk_id]["lexical"] = hit

    fused: list[FusedHit] = []
    for entry in by_chunk.values():
        dense_hit: Hit | None = entry.get("dense")  # type: ignore[assignment]
        lexical_hit: Hit | None = entry.get("lexical")  # type: ignore[assignment]
        score = 0.0
        if dense_hit is not None:
            score += 1.0 / (k + dense_hit.rank)
        if lexical_hit is not None:
            score += 1.0 / (k + lexical_hit.rank)
        fused.append(
            FusedHit(
                hit=entry["hit"],  # type: ignore[arg-type]
                rrf_score=score,
                dense_rank=dense_hit.rank if dense_hit else None,
                dense_similarity=dense_hit.score if dense_hit else None,
                lexical_rank=lexical_hit.rank if lexical_hit else None,
                lexical_score=lexical_hit.score if lexical_hit else None,
            )
        )

    # chunk_id breaks ties so that an unchanged corpus and query always fuse to
    # the same order; without it dict iteration order would leak into results.
    fused.sort(key=lambda f: (-f.rrf_score, f.hit.chunk_id))
    return fused
