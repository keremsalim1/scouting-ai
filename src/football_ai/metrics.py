"""Load and validate config/metrics.yaml.

The yaml is the source of truth for metric definitions, so it is validated
before anything is loaded: a typo in `unit` or a missing `higher_is_better`
should fail here with a readable message, not silently produce a metric that
ranks the wrong way round.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from football_ai.data.db import REPO_ROOT

METRICS_PATH = REPO_ROOT / "config" / "metrics.yaml"

VALID_UNITS = {"per90", "percent", "ratio", "count"}
VALID_FALLBACKS = {"pool_leagues_keep_role"}
VALID_PERCENTILE_METHODS = {"midrank"}
REQUIRED_FIELDS = (
    "key",
    "column",
    "label",
    "definition",
    "formula",
    "unit",
    "higher_is_better",
    "category",
)


@dataclass(frozen=True)
class Metric:
    key: str
    source_column: str
    label: str
    definition: str
    formula: str
    unit: str
    higher_is_better: bool
    category: str
    sort_order: int


@dataclass(frozen=True)
class MetricsConfig:
    version: int
    min_minutes: int
    min_group_size: int
    percentile_method: str
    fallback: str
    categories: dict[str, str]
    metrics: tuple[Metric, ...]

    @property
    def keys(self) -> set[str]:
        return {m.key for m in self.metrics}

    @property
    def config_values(self) -> dict[str, float]:
        """The thresholds that go into football.metric_config."""
        return {
            "min_minutes": float(self.min_minutes),
            "min_group_size": float(self.min_group_size),
        }


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        msg = f"{where}: missing required field {key!r}"
        raise ValueError(msg)
    return mapping[key]


def parse(raw: dict[str, Any]) -> MetricsConfig:
    """Validate a parsed yaml document and turn it into a MetricsConfig."""
    defaults = _require(raw, "defaults", "metrics.yaml")
    pct = _require(raw, "percentile", "metrics.yaml")
    categories = _require(raw, "categories", "metrics.yaml")

    method = _require(pct, "method", "metrics.yaml percentile")
    if method not in VALID_PERCENTILE_METHODS:
        msg = (
            f"metrics.yaml percentile.method: {method!r} not in {sorted(VALID_PERCENTILE_METHODS)}"
        )
        raise ValueError(msg)

    fallback = _require(pct, "fallback", "metrics.yaml percentile")
    if fallback not in VALID_FALLBACKS:
        msg = f"metrics.yaml percentile.fallback: {fallback!r} not in {sorted(VALID_FALLBACKS)}"
        raise ValueError(msg)

    min_group_size = int(_require(pct, "min_group_size", "metrics.yaml percentile"))
    if min_group_size < 2:
        msg = f"metrics.yaml percentile.min_group_size must be at least 2, got {min_group_size}"
        raise ValueError(msg)

    min_minutes = int(_require(defaults, "min_minutes", "metrics.yaml defaults"))
    if min_minutes < 0:
        msg = f"metrics.yaml defaults.min_minutes must not be negative, got {min_minutes}"
        raise ValueError(msg)

    entries = _require(raw, "metrics", "metrics.yaml")
    if not entries:
        msg = "metrics.yaml: no metrics defined"
        raise ValueError(msg)

    metrics: list[Metric] = []
    seen: set[str] = set()
    for order, entry in enumerate(entries):
        where = f"metrics.yaml metric #{order + 1}"
        for field in REQUIRED_FIELDS:
            _require(entry, field, where)
        key = entry["key"]
        if key in seen:
            msg = f"{where}: duplicate metric key {key!r}"
            raise ValueError(msg)
        seen.add(key)
        if entry["unit"] not in VALID_UNITS:
            msg = f"{where} ({key}): unit {entry['unit']!r} not in {sorted(VALID_UNITS)}"
            raise ValueError(msg)
        if not isinstance(entry["higher_is_better"], bool):
            msg = f"{where} ({key}): higher_is_better must be true or false"
            raise ValueError(msg)
        if entry["category"] not in categories:
            msg = (
                f"{where} ({key}): category {entry['category']!r} is not declared "
                f"under `categories`"
            )
            raise ValueError(msg)
        metrics.append(
            Metric(
                key=key,
                source_column=entry["column"],
                label=entry["label"],
                definition=" ".join(str(entry["definition"]).split()),
                formula=entry["formula"],
                unit=entry["unit"],
                higher_is_better=entry["higher_is_better"],
                category=entry["category"],
                sort_order=order,
            )
        )

    return MetricsConfig(
        version=int(_require(raw, "version", "metrics.yaml")),
        min_minutes=min_minutes,
        min_group_size=min_group_size,
        percentile_method=method,
        fallback=fallback,
        categories=dict(categories),
        metrics=tuple(metrics),
    )


def load(path: Path | None = None) -> MetricsConfig:
    text = (path or METRICS_PATH).read_text(encoding="utf-8")
    return parse(yaml.safe_load(text))
