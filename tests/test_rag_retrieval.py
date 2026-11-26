"""methodology_search: modes, abstention, citation. No database, no models."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pytest

from football_ai.rag import retrieval
from football_ai.rag.config import RagConfig
from football_ai.rag.config import load as load_config
from football_ai.rag.retrieval import ABSTAIN_MESSAGE, methodology_search
from football_ai.rag.search import Hit


def _cfg(**overrides: Any) -> RagConfig:
    return dataclasses.replace(load_config(), **overrides)


def _hit(rank: int, doc_id: str, score: float = 0.9) -> Hit:
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


def _embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 1024), dtype=np.float32)


class _ExplodingConnection:
    """Any database use at all is a failure for the tests that use this."""

    def cursor(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("the database must not be touched here")


class _FakeSearch:
    def __init__(self) -> None:
        self.dense: list[Hit] = []
        self.lexical: list[Hit] = []
        self.config_checked = False


@pytest.fixture
def fake_search(monkeypatch: pytest.MonkeyPatch) -> _FakeSearch:
    state = _FakeSearch()

    def dense_search(_conn, _embedding, *, limit):
        return state.dense[:limit]

    def lexical_search(_conn, _query, *, limit, text_search_config):
        return state.lexical[:limit]

    def assert_text_search_config(_conn, expected):
        state.config_checked = True

    monkeypatch.setattr(retrieval, "dense_search", dense_search)
    monkeypatch.setattr(retrieval, "lexical_search", lexical_search)
    monkeypatch.setattr(retrieval, "assert_text_search_config", assert_text_search_config)
    return state


def test_empty_query_abstains_without_calling_the_models():
    calls: list[list[str]] = []

    def recording_embed(texts: list[str]) -> np.ndarray:
        calls.append(texts)
        return _embed(texts)

    result = methodology_search(
        _ExplodingConnection(), "   ", embed_fn=recording_embed, mode="dense"
    )
    assert result.abstained
    assert result.passages == []
    assert result.abstain_reason
    assert calls == []


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        methodology_search(_ExplodingConnection(), "q", embed_fn=_embed, mode="rerank_only")


def test_hybrid_rerank_without_a_rerank_fn_is_rejected():
    with pytest.raises(ValueError, match="rerank_fn"):
        methodology_search(_ExplodingConnection(), "q", embed_fn=_embed, mode="hybrid_rerank")


def test_dense_mode_abstains_below_the_similarity_threshold(fake_search):
    fake_search.dense = [_hit(1, "a", score=0.21)]
    result = methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        mode="dense",
        config=_cfg(dense_abstain_threshold=0.5),
    )
    assert result.abstained
    assert result.relevance_signal == "dense_similarity"
    assert result.relevance_score == pytest.approx(0.21)
    assert result.threshold == 0.5


def test_dense_mode_returns_top_n_above_the_threshold(fake_search):
    fake_search.dense = [_hit(i, f"d{i}", score=0.9 - i / 100) for i in range(1, 11)]
    result = methodology_search(object(), "q", embed_fn=_embed, mode="dense", config=_cfg(top_n=5))
    assert not result.abstained
    assert len(result.passages) == 5
    assert all(p.source and p.title for p in result.passages)
    assert all(p.rrf_score is None and p.rerank_score is None for p in result.passages)


def test_dense_mode_does_not_check_the_text_search_config(fake_search):
    # dense mode never touches content_tsv, so the schema check is not its
    # business - and day 11 must be able to run it on a database without 009
    fake_search.dense = [_hit(1, "a")]
    methodology_search(object(), "q", embed_fn=_embed, mode="dense")
    assert fake_search.config_checked is False


def test_hybrid_mode_checks_the_text_search_config(fake_search):
    # without this the mismatch guard is silent dead code
    fake_search.dense = [_hit(1, "a")]
    methodology_search(object(), "q", embed_fn=_embed, mode="hybrid")
    assert fake_search.config_checked is True


def test_hybrid_mode_scores_relevance_over_all_dense_candidates(fake_search):
    # "weak" is in both lists (1/61 + 1/62) so fusion puts it first and the
    # strongest dense hit ("strong", 1/61) falls outside top_n=1. The returned
    # passage's own similarity is 0.10, well under the threshold - if the
    # signal were read off the returned passages this would abstain.
    fake_search.dense = [_hit(1, "strong", score=0.77), _hit(2, "weak", score=0.10)]
    fake_search.lexical = [_hit(1, "weak", score=0.03)]
    result = methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        mode="hybrid",
        config=_cfg(top_n=1, dense_abstain_threshold=0.5),
    )
    assert not result.abstained
    assert result.relevance_score == pytest.approx(0.77)
    assert [p.doc_id for p in result.passages] == ["weak"]
    assert result.passages[0].dense_similarity == pytest.approx(0.10)


def test_hybrid_mode_returns_a_lexical_only_passage_without_a_dense_score(fake_search):
    # the threshold lookup must not assume every returned passage has a dense
    # score; a lexical-only hit legitimately has none
    fake_search.dense = [_hit(1, "both", score=0.77)]
    fake_search.lexical = [_hit(1, "both", score=0.03), _hit(2, "lex-only", score=0.01)]
    result = methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        mode="hybrid",
        config=_cfg(top_n=2, dense_abstain_threshold=0.5),
    )
    assert not result.abstained
    lex_only = next(p for p in result.passages if p.doc_id == "lex-only")
    assert lex_only.dense_similarity is None
    assert lex_only.lexical_rank == 2


def test_dense_and_hybrid_agree_on_abstention_for_the_same_query(fake_search):
    # the regression this guards: fusion must not be able to flip the abstain
    # decision, or day 11's ablation measures ranking and abstention at once
    fake_search.dense = [_hit(1, "x", score=0.77), _hit(2, "y", score=0.10)]
    fake_search.lexical = [
        _hit(1, "a", score=0.03),
        _hit(2, "b", score=0.02),
        _hit(3, "y", score=0.01),
    ]
    cfg = _cfg(top_n=2, dense_abstain_threshold=0.5)
    both = [
        methodology_search(object(), "q", embed_fn=_embed, mode=mode, config=cfg)
        for mode in ("dense", "hybrid")
    ]
    assert {r.abstained for r in both} == {False}
    assert {round(r.relevance_score, 6) for r in both} == {0.77}


def test_hybrid_mode_abstains_when_the_dense_list_is_empty(fake_search):
    fake_search.dense = []
    fake_search.lexical = [_hit(1, "a", score=0.03)]
    result = methodology_search(object(), "q", embed_fn=_embed, mode="hybrid")
    assert result.abstained
    assert result.relevance_score is None


def test_hybrid_rerank_reorders_the_fused_candidates(fake_search):
    fake_search.dense = [_hit(1, "a"), _hit(2, "b")]
    fake_search.lexical = []
    result = methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        rerank_fn=lambda _q, _ps: np.array([0.1, 0.95], dtype=np.float32),
        mode="hybrid_rerank",
        config=_cfg(rerank_abstain_threshold=0.5),
    )
    assert [p.doc_id for p in result.passages] == ["b", "a"]
    assert result.relevance_signal == "rerank_score"
    assert result.relevance_score == pytest.approx(0.95)
    assert result.passages[0].rerank_score == pytest.approx(0.95)


def test_hybrid_rerank_abstains_when_the_best_rerank_score_is_low(fake_search):
    fake_search.dense = [_hit(1, "a")]
    result = methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        rerank_fn=lambda _q, _ps: np.array([0.12], dtype=np.float32),
        mode="hybrid_rerank",
        config=_cfg(rerank_abstain_threshold=0.5),
    )
    assert result.abstained
    assert result.passages == []
    assert ABSTAIN_MESSAGE in result.abstain_reason


def test_reranker_sees_only_rerank_candidates_not_every_fused_row(fake_search):
    fake_search.dense = [_hit(i, f"d{i}") for i in range(1, 31)]
    seen: dict[str, int] = {}

    def rerank_fn(_q: str, passages: list[str]) -> np.ndarray:
        seen["n"] = len(passages)
        return np.ones(len(passages), dtype=np.float32)

    methodology_search(
        object(),
        "q",
        embed_fn=_embed,
        rerank_fn=rerank_fn,
        mode="hybrid_rerank",
        config=_cfg(rerank_candidates=20),
    )
    assert seen["n"] == 20
