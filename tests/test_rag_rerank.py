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
    Reranker(model=fake, output_scale="logit").score("q", ["p1", "p2"])
    assert fake.seen == [("q", "p1"), ("q", "p2")]


def test_score_is_not_affected_by_which_other_passages_share_the_batch():
    """A relevance score must be a function of (query, passage), nothing else.

    Inferring the scale from the observed values made it batch-dependent: one
    weakly-negative candidate flipped the whole batch into the sigmoid branch
    and nearly doubled an unrelated passage's reported score, so
    `rerank_score` could not be compared across queries - the one thing a
    relevance score is for.
    """
    alone = Reranker(model=_FakeCrossEncoder([0.30, 0.40]), output_scale="logit").score(
        "q", ["a", "b"]
    )
    with_neighbour = Reranker(
        model=_FakeCrossEncoder([0.30, 0.40, -0.01]), output_scale="logit"
    ).score("q", ["a", "b", "c"])
    assert alone[0] == pytest.approx(with_neighbour[0])
    assert alone[1] == pytest.approx(with_neighbour[1])


def test_score_is_monotone_in_the_model_output():
    # inferring the scale per batch made a HIGHER model output produce a LOWER
    # score across the [0, 1] boundary: 0.99 -> 0.99 but 1.01 -> 0.733
    lower = Reranker(model=_FakeCrossEncoder([0.99]), output_scale="logit").score("q", ["a"])
    higher = Reranker(model=_FakeCrossEncoder([1.01]), output_scale="logit").score("q", ["a"])
    assert higher[0] > lower[0]


def test_score_rejects_output_that_contradicts_the_declared_scale():
    # a library or model-config change that starts emitting logits must be
    # loud, not silently rescaled
    with pytest.raises(ValueError, match="probability"):
        Reranker(model=_FakeCrossEncoder([4.0])).score("q", ["a"])


def test_score_passes_through_output_that_is_already_a_probability():
    """Do not squash twice.

    sentence-transformers applies bge-reranker's own sigmoid inside
    `predict()`, so the raw output is already in [0, 1]. Applying another
    sigmoid maps [0, 1] onto [0.5, 0.731] and destroys the discrimination the
    cross-encoder exists to provide: against the real corpus every
    out-of-corpus passage came back as exactly 0.500 and the best in-corpus
    passage as 0.726 - which is sigmoid(0.97), i.e. a 0.97 probability
    silently compressed.
    """
    out = Reranker(model=_FakeCrossEncoder([0.97, 0.0003, 0.5])).score("q", ["a", "b", "c"])
    assert out[0] == pytest.approx(0.97)
    assert out[1] == pytest.approx(0.0003)
    assert out[2] == pytest.approx(0.5)


def test_score_maps_logits_through_a_sigmoid():
    # raw bge-reranker output is an unbounded logit; a threshold in
    # config/rag.yaml has to be a readable number, so it is squashed to [0, 1]
    out = Reranker(model=_FakeCrossEncoder([0.0, 4.0, -4.0]), output_scale="logit").score(
        "q", ["a", "b", "c"]
    )
    assert out[0] == pytest.approx(0.5)
    assert out[1] > 0.98
    assert out[2] < 0.02
    assert out.dtype == np.float32


def test_score_preserves_the_order_of_the_logits():
    out = Reranker(model=_FakeCrossEncoder([-1.0, 3.0, 1.0]), output_scale="logit").score(
        "q", list("abc")
    )
    assert list(np.argsort(-out)) == [1, 2, 0]


def test_score_of_no_passages_is_an_empty_array_without_loading_a_model():
    # no model injected: returning early must happen before any import or
    # download, or every empty-candidate call would pay for the model
    out = Reranker().score("q", [])
    assert out.shape == (0,)


def test_score_rejects_a_mismatched_model_output_length():
    with pytest.raises(ValueError, match="2"):
        Reranker(model=_FakeCrossEncoder([1.0])).score("q", ["a", "b"])
