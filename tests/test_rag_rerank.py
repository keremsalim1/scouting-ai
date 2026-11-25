"""bge-reranker-v2-m3 cross-encoder wrapper.

A fake cross-encoder is injected everywhere: the real model is ~600 MB and CI
never downloads one (the day-6 rule, applied to RAG in D-034).
"""

from __future__ import annotations

import numpy as np
import pytest

from football_ai.rag.rerank import Reranker


class _FakeCrossEncoder:
    def __init__(self, logits: list[float]) -> None:
        self.logits = logits
        self.seen: list[tuple[str, str]] | None = None

    def predict(self, pairs, **_kwargs):
        self.seen = list(pairs)
        return np.asarray(self.logits, dtype=np.float32)


def test_score_pairs_the_query_with_every_passage():
    fake = _FakeCrossEncoder([1.0, -2.0])
    Reranker(model=fake).score("q", ["p1", "p2"])
    assert fake.seen == [("q", "p1"), ("q", "p2")]


def test_score_maps_logits_through_a_sigmoid():
    # raw bge-reranker output is an unbounded logit; a threshold in
    # config/rag.yaml has to be a readable number, so it is squashed to [0, 1]
    out = Reranker(model=_FakeCrossEncoder([0.0, 4.0, -4.0])).score("q", ["a", "b", "c"])
    assert out[0] == pytest.approx(0.5)
    assert out[1] > 0.98
    assert out[2] < 0.02
    assert out.dtype == np.float32


def test_score_preserves_the_order_of_the_logits():
    out = Reranker(model=_FakeCrossEncoder([-1.0, 3.0, 1.0])).score("q", list("abc"))
    assert list(np.argsort(-out)) == [1, 2, 0]


def test_score_of_no_passages_is_an_empty_array_without_loading_a_model():
    # no model injected: returning early must happen before any import or
    # download, or every empty-candidate call would pay for the model
    out = Reranker().score("q", [])
    assert out.shape == (0,)


def test_score_rejects_a_mismatched_model_output_length():
    with pytest.raises(ValueError, match="2"):
        Reranker(model=_FakeCrossEncoder([1.0])).score("q", ["a", "b"])
