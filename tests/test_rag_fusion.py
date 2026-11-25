"""Reciprocal rank fusion over the two retrievers' ranked lists."""

from __future__ import annotations

import pytest

from football_ai.rag.fusion import fuse
from football_ai.rag.search import Hit


def _hit(rank: int, doc_id: str, score: float = 0.5) -> Hit:
    # chunk_id derives from doc_id so the same chunk is recognised across the
    # two lists, exactly as the real rows are matched by primary key.
    return Hit(
        chunk_id=abs(hash(doc_id)) % 10_000,
        doc_id=doc_id,
        chunk_index=0,
        topic="shooting",
        source="test",
        title=f"{doc_id} title",
        content="body",
        score=score,
        rank=rank,
    )


def test_fuse_scores_a_hit_in_both_lists_higher_than_either_alone():
    # a: dense 1, lexical 3 -> 1/61 + 1/63 ; b: dense 2 only -> 1/62
    fused = fuse(
        [_hit(1, "a"), _hit(2, "b")],
        [_hit(1, "c"), _hit(2, "d"), _hit(3, "a")],
        k=60,
    )
    assert fused[0].hit.doc_id == "a"
    assert fused[0].rrf_score == pytest.approx(1 / 61 + 1 / 63)


def test_fuse_carries_both_ranks_and_both_scores():
    fused = fuse([_hit(1, "a", score=0.8)], [_hit(1, "a", score=0.02)], k=60)
    only = fused[0]
    assert (only.dense_rank, only.lexical_rank) == (1, 1)
    assert (only.dense_similarity, only.lexical_score) == (0.8, 0.02)


def test_fuse_leaves_the_other_retrievers_fields_none_for_a_single_list_hit():
    fused = fuse([_hit(1, "a")], [], k=60)
    assert fused[0].lexical_rank is None
    assert fused[0].lexical_score is None
    assert fused[0].dense_rank == 1


def test_fuse_of_two_empty_lists_is_empty():
    assert fuse([], [], k=60) == []


def test_fuse_ignores_score_magnitude_entirely():
    # ts_rank is unbounded and cosine is not; fusion must read ranks only
    a = fuse([_hit(1, "a", score=0.9)], [_hit(1, "b", score=0.01)], k=60)
    b = fuse([_hit(1, "a", score=0.9)], [_hit(1, "b", score=99.0)], k=60)
    assert [h.hit.doc_id for h in a] == [h.hit.doc_id for h in b]


def test_fuse_is_deterministic_on_tied_scores():
    # every chunk here scores 1/61 + 1/62, so only the tie-break orders them
    fused = fuse(
        [_hit(1, "b"), _hit(2, "a")],
        [_hit(1, "a"), _hit(2, "b")],
        k=60,
    )
    assert [h.hit.chunk_id for h in fused] == sorted(h.hit.chunk_id for h in fused)


def test_fuse_returns_every_candidate_unsliced():
    dense = [_hit(i, f"d{i}") for i in range(1, 6)]
    lexical = [_hit(i, f"l{i}") for i in range(1, 6)]
    assert len(fuse(dense, lexical, k=60)) == 10
