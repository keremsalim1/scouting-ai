"""What the gold set does NOT ask about.

The first real run made the case for this module: `match_detail` scored 0% and
nobody had predicted it. A gold set written by one person in one sitting covers
that person's imagination, and "write more questions" is not a plan. This turns
the gap into a list with names in it.

Two axes, both mechanical and free - no LLM, no data, so it runs in CI:

* **Relations.** Which of the readable relations does no reference query touch?
  `lineups` and `player_match_stats` hold real scouting questions ("how many
  matches did he start on the bench?", "his numbers in that one match") and the
  first 40 questions never went near either.
* **Metrics.** Which of the keys in `config/metrics.yaml` does no question
  filter `player_metrics` on? 38 metrics exist; a benchmark that exercises five
  of them is measuring the view, not the metric layer.

Coverage is a floor, not a target. Touching every relation once proves nothing
about depth, and chasing 100% would reward breadth over the error-driven
questions that actually carry signal.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from football_ai.data.db import ALLOWED_RELATIONS
from football_ai.evals.sql import structure
from football_ai.evals.sql.goldset import GoldSet
from football_ai.metrics import load as load_metrics
from football_ai.sql_agent import guard

# Catalog and config relations: askable in principle ("which metrics exist?"),
# but a gap here is bookkeeping rather than a missing scouting question, so
# they are reported separately from the fact tables and views.
METADATA_RELATIONS: frozenset[str] = frozenset(
    {"data_quality", "data_quality_features", "metric_config", "metric_definitions"}
)


def relations_touched(gold: GoldSet) -> frozenset[str]:
    """Relation names at least one reference query reads."""
    found: set[str] = set()
    for question in gold.questions:
        if question.reference_sql:
            found |= structure.relations_used(question.reference_sql)
    return frozenset(found)


def relation_gaps(gold: GoldSet, *, include_metadata: bool = False) -> tuple[str, ...]:
    """Readable relations no question touches, in catalog order."""
    touched = relations_touched(gold)
    return tuple(
        name
        for name in ALLOWED_RELATIONS
        if name not in touched and (include_metadata or name not in METADATA_RELATIONS)
    )


def metrics_touched(gold: GoldSet) -> frozenset[str]:
    """Metric keys a reference query filters `player_metrics` on.

    Read from the tree rather than by searching the text, so a key appearing
    in a comment or an alias does not count as coverage.
    """
    found: set[str] = set()
    for question in gold.questions:
        if not question.reference_sql:
            continue
        try:
            tree = sqlglot.parse_one(question.reference_sql, dialect=guard.DIALECT)
        except sqlglot.ParseError:  # pragma: no cover - the gold check rejects these first
            continue
        for comparison in tree.find_all(exp.EQ):
            left, right = comparison.this, comparison.expression
            if (
                isinstance(left, exp.Column)
                and (left.name or "").lower() == "metric"
                and isinstance(right, exp.Literal)
                and right.is_string
            ):
                found.add(right.this)
    return frozenset(found)


def metric_gaps(gold: GoldSet) -> tuple[str, ...]:
    """Metric keys from config/metrics.yaml that no question asks about."""
    touched = metrics_touched(gold)
    return tuple(m.key for m in load_metrics().metrics if m.key not in touched)


def summary(gold: GoldSet) -> list[str]:
    """Report lines for the gold-set validator."""
    relations = relations_touched(gold)
    countable = [r for r in ALLOWED_RELATIONS if r not in METADATA_RELATIONS]
    metric_keys = [m.key for m in load_metrics().metrics]
    touched_metrics = metrics_touched(gold)

    lines = [
        f"  ilişki kapsamı  {len(relations & frozenset(countable))}/{len(countable)}",
        f"  metrik kapsamı  {len(touched_metrics)}/{len(metric_keys)}",
    ]
    gaps = relation_gaps(gold)
    if gaps:
        lines.append(f"  sorusu olmayan ilişkiler: {', '.join(gaps)}")
    return lines
