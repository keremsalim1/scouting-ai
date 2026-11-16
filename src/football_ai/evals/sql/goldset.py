"""Load and validate evals/sql/questions.yaml.

The gold set is the authority for what the benchmark measures, so it is
validated before anything runs: an unknown category, a duplicate id or a
reference query that is missing where one is required should fail here with
the offending question id in the message. The alternative is a question that
is silently scored against the wrong rules, which shows up as a wrong accuracy
number rather than as a bug.

`parse` is kept separate from `load` for the same reason as in
``football_ai.metrics``: every validation rule can then be tested without
touching the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from football_ai.data.db import REPO_ROOT

QUESTIONS_PATH = REPO_ROOT / "evals" / "sql" / "questions.yaml"

# The eight categories the benchmark reports separately. A single overall
# accuracy says nothing actionable; "ratios 40%, totals 95%" says which part of
# the prompt is missing.
CATEGORIES: tuple[str, ...] = (
    "totals",
    "rates",
    "percentiles",
    "transfers",
    "teams",
    "match_detail",
    "filters",
    "unanswerable",
)

# Structures a question forbids. `minutes_filter` is a predicate; the rest are
# relation names, checked against the relations the query actually reads.
FORBIDDEN_CHECKS: tuple[str, ...] = (
    "minutes_filter",
    "player_season",
    "player_season_club",
    "player_metrics",
    "player_per90",
)

# The category with no reference result set: the question asks for something
# the database does not hold, so only "did it run" and "did it avoid the
# forbidden shapes" can be scored.
UNANSWERABLE = "unanswerable"

REQUIRED_FIELDS = ("id", "question", "category", "order_sensitive")


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        msg = f"{where}: missing required field {key!r}"
        raise ValueError(msg)
    return mapping[key]


@dataclass(frozen=True)
class Question:
    """One benchmark question and the rules for scoring it."""

    id: str
    question: str
    category: str
    reference_sql: str | None
    order_sensitive: bool
    required_columns: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    notes: str = ""

    @property
    def scores_correctness(self) -> bool:
        """Does this question count towards the accuracy denominator?

        `unanswerable` questions do not: there is no reference result set to
        compare against, so including them would mix "the model got the number
        wrong" with "there was no number to get".
        """
        return self.category != UNANSWERABLE


@dataclass(frozen=True)
class GoldSet:
    questions: tuple[Question, ...]

    def by_category(self) -> dict[str, tuple[Question, ...]]:
        """Questions grouped by category, in file order within each group."""
        grouped: dict[str, list[Question]] = {}
        for question in self.questions:
            grouped.setdefault(question.category, []).append(question)
        return {name: tuple(items) for name, items in grouped.items()}

    def get(self, qid: str) -> Question:
        for question in self.questions:
            if question.id == qid:
                return question
        msg = f"no such question: {qid!r}"
        raise KeyError(msg)

    def select(
        self,
        *,
        category: str | None = None,
        ids: tuple[str, ...] | None = None,
    ) -> tuple[Question, ...]:
        """Narrow the suite, so one category can be re-run without paying for 40.

        `ids` keeps the caller's order and raises on an unknown id: a typo that
        silently ran zero questions would be reported as 0% accuracy.
        """
        if ids is not None:
            return tuple(self.get(qid) for qid in ids)
        if category is not None:
            return tuple(q for q in self.questions if q.category == category)
        return self.questions


def _parse_question(raw: Any, index: int) -> Question:
    if not isinstance(raw, dict):
        msg = f"question #{index + 1}: expected a mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    # The id is read first so every later message can name the question.
    where = f"question {raw.get('id', f'#{index + 1}')!r}"
    for field in REQUIRED_FIELDS:
        _require(raw, field, where)

    qid = str(raw["id"])
    category = str(raw["category"])
    if category not in CATEGORIES:
        msg = f"{where}: unknown category {category!r}; known: {', '.join(CATEGORIES)}"
        raise ValueError(msg)

    reference_sql = raw.get("reference_sql")
    if category != UNANSWERABLE and not reference_sql:
        msg = f"{where}: reference_sql is required for category {category!r}"
        raise ValueError(msg)

    forbidden = tuple(str(name) for name in raw.get("forbidden") or ())
    unknown = [name for name in forbidden if name not in FORBIDDEN_CHECKS]
    if unknown:
        msg = (
            f"{where}: unknown forbidden check(s) {', '.join(repr(u) for u in unknown)}; "
            f"known: {', '.join(FORBIDDEN_CHECKS)}"
        )
        raise ValueError(msg)

    return Question(
        id=qid,
        question=str(raw["question"]),
        category=category,
        reference_sql=str(reference_sql) if reference_sql else None,
        order_sensitive=bool(raw["order_sensitive"]),
        required_columns=tuple(str(c) for c in raw.get("required_columns") or ()),
        forbidden=forbidden,
        notes=str(raw.get("notes") or ""),
    )


def parse(raw: list[Any]) -> GoldSet:
    """Validate a parsed yaml document and turn it into a GoldSet."""
    if not isinstance(raw, list):
        msg = f"the gold set must be a list of questions, got {type(raw).__name__}"
        raise ValueError(msg)
    if not raw:
        msg = "the gold set is empty"
        raise ValueError(msg)

    questions = tuple(_parse_question(item, i) for i, item in enumerate(raw))

    seen: set[str] = set()
    for question in questions:
        if question.id in seen:
            msg = f"duplicate question id {question.id!r}"
            raise ValueError(msg)
        seen.add(question.id)

    return GoldSet(questions=questions)


def load(path: Path | None = None) -> GoldSet:
    text = (path or QUESTIONS_PATH).read_text(encoding="utf-8")
    return parse(yaml.safe_load(text))
