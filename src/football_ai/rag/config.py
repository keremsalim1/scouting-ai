"""Load and validate config/rag.yaml.

Retrieval parameters are runtime authority, the same posture metrics.py takes
for config/metrics.yaml: day 11 tunes thresholds and candidate depths while
measuring, so a change there must not need a code edit.

Validated on load rather than trusted, because the failure mode of a bad
value here is silent: a `top_n` above the candidate depth truncates results
without an error, and a threshold outside [0, 1] either abstains on
everything or never abstains at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from football_ai.data.db import REPO_ROOT

RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag.yaml"

# The three ablation modes day 11 compares. Declared here rather than in
# retrieval.py so the config loader and the tool agree on one list.
VALID_MODES: frozenset[str] = frozenset({"dense", "hybrid", "hybrid_rerank"})

_POSITIVE_INTS = (
    "rrf_k",
    "dense_candidates",
    "lexical_candidates",
    "rerank_candidates",
    "top_n",
)
_UNIT_FLOATS = ("dense_abstain_threshold", "rerank_abstain_threshold")
_NON_EMPTY_STRINGS = ("text_search_config", "rerank_model")


@dataclass(frozen=True)
class RagConfig:
    version: int
    text_search_config: str
    rrf_k: int
    dense_candidates: int
    lexical_candidates: int
    rerank_candidates: int
    top_n: int
    dense_abstain_threshold: float
    rerank_abstain_threshold: float
    rerank_model: str


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        msg = f"{where}: missing required field {key!r}"
        raise ValueError(msg)
    return mapping[key]


def parse(raw: dict[str, Any]) -> RagConfig:
    """Validate a parsed yaml document and turn it into a RagConfig."""
    where = "rag.yaml"
    version = int(_require(raw, "version", where))

    values: dict[str, Any] = {"version": version}

    for key in _POSITIVE_INTS:
        value = _require(raw, key, where)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            msg = f"{where}: {key} must be a positive integer, got {value!r}"
            raise ValueError(msg)
        values[key] = value

    for key in _UNIT_FLOATS:
        value = float(_require(raw, key, where))
        if not 0.0 <= value <= 1.0:
            msg = f"{where}: {key} must be in [0.0, 1.0], got {value!r}"
            raise ValueError(msg)
        values[key] = value

    for key in _NON_EMPTY_STRINGS:
        value = _require(raw, key, where)
        if not isinstance(value, str) or not value.strip():
            msg = f"{where}: {key} must be a non-empty string, got {value!r}"
            raise ValueError(msg)
        values[key] = value

    retriever_depth = min(values["dense_candidates"], values["lexical_candidates"])
    if values["top_n"] > retriever_depth:
        msg = (
            f"{where}: top_n ({values['top_n']}) exceeds the shallower retriever "
            f"depth ({retriever_depth}); results would be silently truncated"
        )
        raise ValueError(msg)
    if values["top_n"] > values["rerank_candidates"]:
        msg = (
            f"{where}: rerank_candidates ({values['rerank_candidates']}) is below "
            f"top_n ({values['top_n']}); the reranker cannot fill the result set"
        )
        raise ValueError(msg)

    return RagConfig(**values)


def load(path: Path = RAG_CONFIG_PATH) -> RagConfig:
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")))
