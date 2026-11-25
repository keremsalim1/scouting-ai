"""config/rag.yaml loading and validation."""

from __future__ import annotations

from typing import Any

import pytest

from football_ai.rag.config import load, parse


def _valid_raw() -> dict[str, Any]:
    return {
        "version": 1,
        "text_search_config": "simple",
        "rrf_k": 60,
        "dense_candidates": 20,
        "lexical_candidates": 20,
        "rerank_candidates": 20,
        "top_n": 5,
        "dense_abstain_threshold": 0.5,
        "rerank_abstain_threshold": 0.5,
        "rerank_model": "BAAI/bge-reranker-v2-m3",
    }


def test_load_reads_the_repo_config():
    cfg = load()
    assert cfg.text_search_config == "simple"
    assert cfg.rrf_k == 60
    assert cfg.top_n == 5


def test_parse_rejects_missing_field():
    raw = _valid_raw()
    del raw["rrf_k"]
    with pytest.raises(ValueError, match="rrf_k"):
        parse(raw)


def test_parse_rejects_non_positive_rrf_k():
    with pytest.raises(ValueError, match="rrf_k"):
        parse({**_valid_raw(), "rrf_k": 0})


def test_parse_rejects_top_n_above_candidate_depth():
    # top_n larger than what retrieval can supply is a silent truncation bug
    with pytest.raises(ValueError, match="top_n"):
        parse({**_valid_raw(), "top_n": 50})


def test_parse_rejects_rerank_candidates_below_top_n():
    with pytest.raises(ValueError, match="rerank_candidates"):
        parse({**_valid_raw(), "rerank_candidates": 3, "top_n": 5})


@pytest.mark.parametrize("field", ["dense_abstain_threshold", "rerank_abstain_threshold"])
def test_parse_rejects_threshold_outside_unit_interval(field: str):
    with pytest.raises(ValueError, match=field):
        parse({**_valid_raw(), field: 1.4})


def test_parse_rejects_empty_text_search_config():
    with pytest.raises(ValueError, match="text_search_config"):
        parse({**_valid_raw(), "text_search_config": ""})
