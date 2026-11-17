# Day 6 — Text-to-SQL Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 40-question text-to-SQL benchmark that reports accuracy per question category, runs locally against two models, and is protected against schema drift by an LLM-free CI job.

**Architecture:** A gold set in YAML (`evals/sql/questions.yaml`) drives three independent pure layers — a result-set comparator, a sqlglot structural checker, and a runner that calls the existing `generate.text_to_sql`. Both the reference SQL and the model's SQL pass through the same `guard.validate` and execute on the `football_ro` role, so the only difference measured is the SQL itself. A report writer turns one run into a JSON record plus a Markdown table; a separate deterministic entry point validates the gold set with `EXPLAIN` on an empty, migrated database, which is what CI runs.

**Tech Stack:** Python 3.12, pytest, PyYAML, sqlglot (postgres dialect), psycopg 3, LiteLLM (local only), GitHub Actions with a `pgvector/pgvector:pg17` service.

**Spec:** `docs/superpowers/specs/2026-11-16-day6-sql-eval-design.md`

## Global Constraints

- Code, identifiers, docstrings and commit messages in English. Report strings and the gold-set questions are Turkish (the user asks in Turkish).
- Every script that prints must call `football_ai.console.force_utf8()` first — Windows cp1254 otherwise crashes `print()` on Turkish characters.
- Queries execute on `readonly_dsn()` (`football_ro`), never `etl_dsn()`.
- Both reference and candidate SQL run through `guard.validate(sql, max_rows=...)` and the executed statement is `GuardResult.sql`.
- Threshold: `correct` ≥ 70% on the strong model (`gemini/gemini-3.8-flash`). The weak model (`gemini/gemini-3.1-flash-lite`) is reported, never gated.
- `unanswerable` questions are excluded from the `correct` denominator; the denominator is printed.
- `infra_error` questions are excluded from the `correct` denominator. Over 10% triggers a "run not comparable" warning.
- Gold-set questions must not appear in `generate.FEW_SHOT`.
- Tests needing a database carry `@pytest.mark.db`; tests needing the real OpenPlay download carry `@pytest.mark.data`. Default `pytest` excludes both.
- Line length 100, ruff rules as configured in `pyproject.toml`.

## Review Focus

- **psycopg returns `Decimal`, not `float`.** `Decimal("1.5") == 1.5` is `True` in Python but `Decimal("0.1") + Decimal("0.2")` is not `0.30000000000000004`; a numeric column compared against a float literal must go through the tolerance path, not `==`. → Task 2.
- **`None` in an order-insensitive sort key.** Sorting rows containing `None` raises `TypeError: '<' not supported between 'NoneType' and 'str'`, and our ratio metrics return NULL on a zero denominator, so this is common, not exotic. → Task 2.
- **Row-count mismatch.** The "extra columns are fine" rule is about columns only. A candidate returning 10 rows where the reference returns 5 is wrong, and a prefix check written carelessly would pass it. → Task 2.
- **Every question infra-errored.** The denominator becomes 0 and the report divides by it. → Task 6.
- **The model answers with prose, or with nothing.** `extract_sql` returns `""`, the guard refuses an empty query; this must score as incorrect with a readable reason, not raise. → Task 5.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/football_ai/evals/__init__.py` | package marker |
| `src/football_ai/evals/sql/__init__.py` | package marker, re-exports the public names |
| `src/football_ai/evals/sql/goldset.py` | typed loader + validation for `questions.yaml` |
| `src/football_ai/evals/sql/compare.py` | result-set equality, pure, no DB |
| `src/football_ai/evals/sql/structure.py` | sqlglot checks: output columns, relations, minutes filter |
| `src/football_ai/evals/sql/execute.py` | guard + execute one statement on `football_ro`; `EXPLAIN` variant |
| `src/football_ai/evals/sql/runner.py` | per-question and whole-suite orchestration, scoring |
| `src/football_ai/evals/sql/report.py` | JSON + Markdown rendering, disagreement table |
| `evals/sql/questions.yaml` | the 40 questions and their reference SQL |
| `scripts/eval_sql.py` | CLI: the LLM run (local) |
| `scripts/eval_sql_gold.py` | CLI: the deterministic gold-set check (CI) |
| `.github/workflows/ci.yml` | lint / test / gold jobs |
| `tests/test_eval_goldset.py` | Task 1 |
| `tests/test_eval_compare.py` | Task 2 |
| `tests/test_eval_structure.py` | Task 3 |
| `tests/test_eval_gold_db.py` | Task 4, `db`-marked |
| `tests/test_eval_runner.py` | Task 5 |
| `tests/test_eval_report.py` | Task 6 |

---

## Task 1: Gold set loader

**Files:**
- Create: `src/football_ai/evals/__init__.py`, `src/football_ai/evals/sql/__init__.py`, `src/football_ai/evals/sql/goldset.py`
- Test: `tests/test_eval_goldset.py`

**Interfaces:**
- Consumes: `football_ai.metrics.load` as the pattern to follow (`parse(raw)` separate from `load(path)` so tests never touch the filesystem).
- Produces:
  ```python
  CATEGORIES: tuple[str, ...]   # totals, rates, percentiles, transfers, teams,
                                # match_detail, filters, unanswerable
  FORBIDDEN_CHECKS: tuple[str, ...]   # "minutes_filter", "player_season_club",
                                      # "player_season", "player_metrics"

  @dataclass(frozen=True)
  class Question:
      id: str
      question: str
      category: str
      reference_sql: str | None
      order_sensitive: bool
      required_columns: tuple[str, ...]
      forbidden: tuple[str, ...]
      notes: str
      @property
      def scores_correctness(self) -> bool   # category != "unanswerable"

  @dataclass(frozen=True)
  class GoldSet:
      questions: tuple[Question, ...]
      def by_category(self) -> dict[str, tuple[Question, ...]]
      def get(self, qid: str) -> Question
      def select(self, *, category: str | None = None,
                ids: tuple[str, ...] | None = None) -> tuple[Question, ...]

  def parse(raw: list[dict]) -> GoldSet
  def load(path: Path | None = None) -> GoldSet   # default: evals/sql/questions.yaml
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_goldset.py
def _q(**over):
    base = {
        "id": "totals-01",
        "question": "soru",
        "category": "totals",
        "reference_sql": "select 1",
        "order_sensitive": True,
    }
    return {**base, **over}


def test_parse_defaults_optional_fields():
    gs = goldset.parse([_q()])
    q = gs.questions[0]
    assert q.required_columns == () and q.forbidden == () and q.notes == ""


def test_duplicate_id_is_rejected():
    with pytest.raises(ValueError, match="totals-01"):
        goldset.parse([_q(), _q()])


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError, match="offside"):
        goldset.parse([_q(category="offside")])


def test_unknown_forbidden_check_is_rejected():
    with pytest.raises(ValueError, match="hand_of_god"):
        goldset.parse([_q(forbidden=["hand_of_god"])])


def test_reference_sql_required_except_unanswerable():
    with pytest.raises(ValueError, match="reference_sql"):
        goldset.parse([_q(reference_sql=None)])
    gs = goldset.parse([_q(id="unans-01", category="unanswerable", reference_sql=None)])
    assert gs.questions[0].scores_correctness is False


def test_select_filters_by_category_and_ids():
    gs = goldset.parse([_q(), _q(id="rates-01", category="rates")])
    assert [q.id for q in gs.select(category="rates")] == ["rates-01"]
    assert [q.id for q in gs.select(ids=("totals-01",))] == ["totals-01"]


def test_missing_required_field_names_the_question():
    with pytest.raises(ValueError, match="totals-01"):
        goldset.parse([{k: v for k, v in _q().items() if k != "question"}])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_goldset.py -v`
Expected: FAIL — `ModuleNotFoundError: football_ai.evals`

- [ ] **Step 3: Implement `goldset.py`**

Follow `src/football_ai/metrics.py`: a `_require(mapping, key, where)` helper that raises `ValueError` naming the offending question id, `parse` building the frozen dataclasses, `load` reading YAML with `yaml.safe_load`. `order_sensitive` is required (not defaulted) — getting it wrong silently changes a verdict, so the author must state it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_goldset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/evals tests/test_eval_goldset.py
git commit -m "feat(evals): typed gold set loader for the SQL benchmark"
```

---

## Task 2: Result-set comparator

**Files:**
- Create: `src/football_ai/evals/sql/compare.py`
- Test: `tests/test_eval_compare.py`

**Interfaces:**
- Produces:
  ```python
  TOLERANCE = 1e-6

  @dataclass(frozen=True)
  class Comparison:
      equal: bool
      reason: str = ""      # why not, for the report; "" when equal

  def values_equal(a: object, b: object) -> bool
  def compare(reference: list[tuple], candidate: list[tuple],
              *, order_sensitive: bool) -> Comparison
  ```
  `compare` treats the reference's column count as a prefix width: each candidate row is truncated to `len(reference_row)` before comparison. Row counts must match exactly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_compare.py
def test_decimal_and_float_compare_within_tolerance():
    assert compare.values_equal(Decimal("1.5"), 1.5)
    assert compare.values_equal(Decimal("0.1") + Decimal("0.2"), 0.30000000000000004)
    assert not compare.values_equal(Decimal("1.5"), 1.6)


def test_none_only_equals_none():
    assert compare.values_equal(None, None)
    assert not compare.values_equal(None, 0)
    assert not compare.values_equal(0, None)


def test_extra_trailing_columns_are_allowed():
    ref = [("Saka", 11)]
    cand = [("Saka", 11, 2400)]
    assert compare.compare(ref, cand, order_sensitive=True).equal


def test_missing_column_is_not_equal():
    assert not compare.compare([("Saka", 11)], [("Saka",)], order_sensitive=True).equal


def test_column_names_are_irrelevant_position_is_not():
    assert not compare.compare([("Saka", 11)], [(11, "Saka")], order_sensitive=True).equal


def test_row_count_mismatch_is_not_equal():
    ref = [("a", 1), ("b", 2)]
    cand = [("a", 1), ("b", 2), ("c", 3)]
    out = compare.compare(ref, cand, order_sensitive=False)
    assert not out.equal and "row count" in out.reason


def test_order_matters_only_when_requested():
    ref = [("a", 1), ("b", 2)]
    cand = [("b", 2), ("a", 1)]
    assert not compare.compare(ref, cand, order_sensitive=True).equal
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_order_insensitive_keeps_duplicates():
    assert not compare.compare(
        [("a", 1), ("a", 1)], [("a", 1), ("b", 2)], order_sensitive=False
    ).equal


def test_order_insensitive_sorts_rows_containing_null():
    ref = [("a", None), ("b", 2.0)]
    cand = [("b", 2.0), ("a", None)]
    assert compare.compare(ref, cand, order_sensitive=False).equal


def test_both_empty_is_equal():
    assert compare.compare([], [], order_sensitive=True).equal


def test_reason_names_the_first_differing_row():
    out = compare.compare([("a", 1)], [("a", 2)], order_sensitive=True)
    assert not out.equal and "row 1" in out.reason
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_compare.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `compare.py`**

Two decisions the tests leave open:
- Numeric comparison: convert both sides with `float()` when each is an instance of `(int, float, Decimal)` and neither is `bool`, then `abs(a - b) <= TOLERANCE * max(1.0, abs(b))`. Everything else is plain `==`. `bool` is excluded from the numeric path because `True == 1` would let a boolean column match a count.
- Order-insensitive sorting uses a total-order key per cell: `(value is None, type-rank, normalised value)` where type-rank puts numbers before strings, so `None` and mixed types never reach a `<` between incompatible types.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_compare.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/evals/sql/compare.py tests/test_eval_compare.py
git commit -m "feat(evals): result-set comparator with tolerance and null handling"
```

---

## Task 3: Structural checks

**Files:**
- Create: `src/football_ai/evals/sql/structure.py`
- Test: `tests/test_eval_structure.py`

**Interfaces:**
- Consumes: `goldset.FORBIDDEN_CHECKS` (Task 1), `football_ai.sql_agent.guard.DIALECT`.
- Produces:
  ```python
  def output_columns(sql: str) -> tuple[str, ...]
      # projected names of the outermost SELECT: alias if present, else the
      # column name; `*` yields ("*",)
  def relations_used(sql: str) -> frozenset[str]   # lowercased, CTE names excluded
  def has_minutes_filter(sql: str) -> bool         # minutes_played compared to a number
  def missing_required(sql: str, required: tuple[str, ...]) -> tuple[str, ...]
      # empty when output_columns contains "*"
  def violated_forbidden(sql: str, forbidden: tuple[str, ...]) -> tuple[str, ...]
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_structure.py
def test_output_columns_prefers_alias():
    cols = structure.output_columns("select player, value as npxg from t limit 1")
    assert cols == ("player", "npxg")


def test_output_columns_of_star():
    assert structure.output_columns("select * from t limit 1") == ("*",)


def test_output_columns_reads_the_outermost_select():
    sql = "select name from (select player as name from t) s limit 1"
    assert structure.output_columns(sql) == ("name",)


def test_relations_used_excludes_cte_names():
    sql = "with top as (select player from football.player_season) select player from top limit 1"
    assert structure.relations_used(sql) == frozenset({"player_season"})


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("select 1 from t where minutes_played >= 900 limit 1", True),
        ("select 1 from t where minutes_played > 899 limit 1", True),
        ("select 1 from t having sum(minutes_played) >= 900 limit 1", True),
        ("select 1 from t where comp = 'eng' limit 1", False),
        ("select minutes_played from t limit 1", False),
    ],
)
def test_has_minutes_filter(sql, expected):
    assert structure.has_minutes_filter(sql) is expected


def test_missing_required_is_empty_for_star():
    assert structure.missing_required("select * from t limit 1", ("player", "teams")) == ()


def test_missing_required_lists_absent_columns():
    sql = "select player, value from football.player_metrics limit 1"
    assert structure.missing_required(sql, ("player", "percentile")) == ("percentile",)


def test_violated_forbidden_minutes_filter():
    sql = "select player from football.player_season where minutes_played >= 900 limit 1"
    assert structure.violated_forbidden(sql, ("minutes_filter",)) == ("minutes_filter",)


def test_violated_forbidden_relation():
    sql = "select player from football.player_season_club limit 1"
    assert structure.violated_forbidden(sql, ("player_season_club",)) == ("player_season_club",)


def test_violated_forbidden_empty_when_clean():
    sql = "select player from football.player_season limit 1"
    assert structure.violated_forbidden(sql, ("minutes_filter", "player_season_club")) == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_structure.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `structure.py`**

Parse once with `sqlglot.parse_one(sql, dialect=guard.DIALECT)`. `output_columns` reads `tree.selects` on the outermost `exp.Select` (for a set operation, the left-hand side). `has_minutes_filter` looks for any `exp.Column` named `minutes_played` whose ancestor chain reaches a comparison node (`exp.GT`, `exp.GTE`, `exp.LT`, `exp.LTE`, `exp.EQ`, `exp.Between`). Forbidden names resolve as: `minutes_filter` → `has_minutes_filter`, anything else → membership in `relations_used`.

CTE-name exclusion is shared, not duplicated: rename `guard._cte_names` to a public `guard.cte_names` (one call site to update, `guard._check_relations`) and import it from `structure`. Two copies of "which names are CTEs" would drift the moment one of them learns about recursive CTEs.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_structure.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/evals/sql/structure.py tests/test_eval_structure.py
git commit -m "feat(evals): sqlglot structural checks for required and forbidden shapes"
```

---

## Task 4: The 40 questions and the deterministic gold check

This is the task that gates CI, so it owns both the content and the checker.

**Structure decided during review — one implementation, two entry points.** The data-free checks live in `scripts/eval_sql_gold.py` only; `tests/test_eval_gold_db.py` holds the checks that need loaded data and calls the script's `main()` for the rest. Two copies of the same assertions would drift the first time one of them gained a check.

```
                 scripts/eval_sql_gold.py
                 ├── guard.validate every reference SQL      ─┐
                 ├── execute.explain_sql every reference SQL   │ no data needed
                 ├── no overlap with generate.FEW_SHOT         │ -> CI runs this
                 ├── category counts match the spec            │
                 ├── reference satisfies its own               │
                 │   required_columns                          │
                 └── reference violates no own forbidden      ─┘

                 tests/test_eval_gold_db.py   (@pytest.mark.db)
                 ├── main() returns 0            <- calls the script, no duplication
                 ├── every reference returns rows   ─┐ needs loaded data
                 └── no tie at the ranking cut      ─┘ -> local only
```

**Files:**
- Create: `evals/sql/questions.yaml`, `src/football_ai/evals/sql/execute.py`, `scripts/eval_sql_gold.py`
- Modify: `Makefile` (add `eval-sql-gold` to `.PHONY`, the help text and a recipe)
- Test: `tests/test_eval_gold_db.py`, `tests/test_eval_execute.py`

**Interfaces:**
- Consumes: `goldset.load` (Task 1), `guard.validate`, `db.readonly_dsn`, `db.connect`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Execution:
      ok: bool
      columns: tuple[str, ...] = ()
      rows: list[tuple] = field(default_factory=list)
      sql: str | None = None        # the guard's rewrite, i.e. what actually ran
      error: str | None = None
      guard_refusal: str | None = None
      seconds: float = 0.0

  def run_sql(conn, sql: str, *, max_rows: int = guard.DEFAULT_LIMIT) -> Execution
  def explain_sql(conn, sql: str, *, max_rows: int = guard.DEFAULT_LIMIT) -> Execution
      # guard, then EXPLAIN; validates against the schema with no data present
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_eval_execute.py` — no database, no marker. Covers the branch the db tests never reach:

```python
def test_run_sql_reports_a_guard_refusal_without_touching_the_connection():
    out = execute.run_sql(object(), "delete from football.players")  # not a connection
    assert out.ok is False and out.guard_refusal and out.rows == []


def test_run_sql_returns_the_guards_rewrite_not_the_input():
    out = execute.run_sql(_fake_conn(columns=("n",), rows=[(1,)]), "select 1")
    assert "LIMIT 200" in out.sql.upper()
```

The first test passing `object()` as the connection is the assertion: a refused query must short-circuit before any cursor is opened.

```python
# tests/test_eval_gold_db.py
pytestmark = pytest.mark.db


def test_gold_script_passes():
    """The data-free checks live in the script; this is the only place they
    are asserted from pytest, so the two can never disagree."""
    assert eval_sql_gold.main([]) == 0


def test_every_reference_sql_returns_rows(ro_conn):
    """An empty reference is a gold-set bug: the candidate would match by
    returning nothing at all."""
    empty = [
        q.id
        for q in goldset.load().questions
        if q.reference_sql and not execute.run_sql(ro_conn, q.reference_sql).rows
    ]
    assert empty == []


def test_ranking_questions_have_no_tie_at_the_cut(ro_conn):
    """With a tie on the last returned row, two different answers are both
    correct and the comparator cannot tell them apart."""
    ties = []
    for q in goldset.load().questions:
        if not q.order_sensitive or not q.reference_sql:
            continue
        col = _order_column_index(q.reference_sql)  # test-local, see below
        rows = execute.run_sql(ro_conn, q.reference_sql).rows
        wider = execute.run_sql(ro_conn, _with_limit(q.reference_sql, len(rows) + 1)).rows
        if len(wider) > len(rows) and rows[-1][col] == wider[-1][col]:
            ties.append(q.id)
    assert ties == []
```

The remaining checks are assertions inside `scripts/eval_sql_gold.py`, not pytest functions. Each returns a list of offending question ids and the script prints and fails on any non-empty list:

1. `guard.validate(q.reference_sql)` passes for every question with a reference.
2. `execute.explain_sql(conn, q.reference_sql).ok` for every one of them.
3. No gold question text appears in `generate.FEW_SHOT` (compared stripped and lowercased).
4. Category counts equal the spec's distribution.
5. **Self-consistency, added in review:** `structure.missing_required(q.reference_sql, q.required_columns)` is empty for every question. Otherwise the model is held to a standard the reference itself does not meet, and the failure shows up as a wrong accuracy number rather than as a gold-set bug.
6. **Self-consistency, added in review:** `structure.violated_forbidden(q.reference_sql, q.forbidden)` is empty for every question. A `totals` reference that forbids `minutes_filter` must not itself carry one.

Checks 1, 3, 4, 5 and 6 need no database; 2 needs a migrated schema and no rows.

`ro_conn` is a module-level fixture: `db.connect(db.readonly_dsn())`. Reuse the pattern already in `tests/test_sql_guard_db.py`.

Two test-local helpers for the tie check:
- `_with_limit(sql, n)` → `sqlglot.parse_one(sql, dialect="postgres").limit(n).sql(dialect="postgres")`
- `_order_column_index(sql)` → the position of the first `ORDER BY` expression's name within `structure.output_columns(sql)`. It raises if the ordering column is not projected, which makes "the `ORDER BY` column must appear in the `SELECT` list" an enforced gold-set rule rather than a convention. Add that rule to the author rules in Step 4.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_execute.py -v` then `uv run pytest tests/test_eval_gold_db.py -m db -v`
Expected: FAIL — module not found, then `evals/sql/questions.yaml` does not exist

- [ ] **Step 3: Implement `execute.py`**

`run_sql`: `guard.validate` first; on refusal return `Execution(ok=False, guard_refusal=reason)`. Otherwise execute `result.sql` in a cursor, read `cursor.description` for column names, `fetchall()` for rows, and catch `psycopg.Error` into `error`. `explain_sql` is the same but prefixes `EXPLAIN ` and discards the plan rows — it only reports whether Postgres accepted the statement. Both are called with a connection the caller owns; neither opens or closes one.

- [ ] **Step 4: Write the 40 questions**

Distribution from the spec: `totals` 5, `rates` 6, `percentiles` 5, `transfers` 5, `teams` 5, `match_detail` 5, `filters` 5, `unanswerable` 4. Ids are `<category>-NN`.

Rules for the author:
- Run `make schema-prompt` first and write the reference SQL against those columns and literal values.
- Every reference SQL is run by hand in `make db-shell` and its output read before it goes in the file. **Do not have an LLM write the reference SQL** — then the benchmark would measure agreement with the model it is testing.
- `notes` says what the question is a trap for. This text ends up in the error analysis.
- `forbidden` for `totals`: `minutes_filter`. For `transfers` questions asking about combined totals: `player_season_club`. For per-club splits: `player_season`.
- `required_columns` for `percentiles`: at least `percentile` and `comparison_group_size`.
- Pick `limit` values away from a tie boundary (the test above enforces it).
- In an `order_sensitive` question the `ORDER BY` column must also be in the `SELECT` list — `_order_column_index` raises otherwise.
- `unanswerable` covers: pressures, progressive carries, the 2026/27 season, and one metric not in `metrics.yaml`.
- Write 3 of the 40 in English to expose language sensitivity; mark them in `notes`.

- [ ] **Step 5: Implement `scripts/eval_sql_gold.py` and the Makefile target**

`force_utf8()`, load the gold set, run checks 1-6 above on `readonly_dsn()`, print one line per offending question id with the reason, print a summary, return 0 when all pass and 1 otherwise. `main(argv)` takes an argument list so the db test can call it. A `--execute` flag additionally runs the queries for real (needs loaded data; CI does not use it). Makefile:

```make
eval-sql-gold:
	$(UV) run python scripts/eval_sql_gold.py
```

- [ ] **Step 6: Verify the script and the db tests**

Run: `make eval-sql-gold` then `uv run pytest tests/test_eval_gold_db.py -m db -v`
Expected: `40/40 reference queries valid` with exit code 0, then three passing db tests

- [ ] **Step 7: Commit**

```bash
git add evals/sql/questions.yaml src/football_ai/evals/sql/execute.py \
        scripts/eval_sql_gold.py tests/test_eval_gold_db.py \
        tests/test_eval_execute.py src/football_ai/sql_agent/guard.py Makefile
git commit -m "feat(evals): 40-question SQL gold set and deterministic validator"
```

---

## Task 5: Suite runner and scoring

**Files:**
- Create: `src/football_ai/evals/sql/runner.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `goldset`, `compare`, `structure`, `execute` (Tasks 1–4); `generate.text_to_sql`, `generate.LLMClient`, `generate.SqlResult`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class QuestionResult:
      id: str
      category: str
      question: str
      model: str
      generated_sql: str | None
      executes: bool
      correct: bool | None        # None when the category does not score it
      required_columns: bool
      no_forbidden: bool
      infra_error: bool
      repairs_used: int
      structure_differs: bool     # relations_used differs from the reference
      reason: str                 # why it failed, for the report
      seconds: float
      # Added in review: when the verdict is not fully green, the first 5 rows
      # of each side are kept so a disagreement can be judged from the report
      # instead of re-running both queries by hand. Empty when green.
      reference_rows: tuple[tuple, ...]
      candidate_rows: tuple[tuple, ...]
      reference_failed: bool      # the gold set's own SQL did not execute

  @dataclass(frozen=True)
  class SuiteResult:
      model: str
      started_at: datetime         # UTC
      results: tuple[QuestionResult, ...]
      temperature_supported: bool
      reasoning_effort_supported: bool
      retries_used: int
      @property
      def run_id(self) -> str      # "<UTC %Y%m%dT%H%M%SZ>-<model slug>"

  ROWS_KEPT = 5

  def run_question(question: Question, *, conn, client: LLMClient,
                   max_rows: int = guard.DEFAULT_LIMIT,
                   reference_cache: dict[str, Execution] | None = None) -> QuestionResult
  def run_suite(questions: Sequence[Question], *, conn, client,
                model: str, on_result: Callable[[QuestionResult], None] | None = None,
                max_rows: int = guard.DEFAULT_LIMIT,
                reference_cache: dict[str, Execution] | None = None) -> SuiteResult
  ```
  `reference_cache` is keyed by question id and decided in review: `scripts/eval_sql.py` creates one dict and passes it to every `run_suite` call, so a two-model run executes each reference query once instead of twice. Safe because the season is frozen data.
  `infra_error` is `True` when `text_to_sql` raised rather than returned, i.e. the provider never produced an answer. A question with `infra_error` has `correct=None`.

- [ ] **Step 1: Write the failing tests**

Tests use a stub client (the pattern is already in `tests/test_sql_generate.py`) and a fake executor injected by monkeypatching `runner.execute.run_sql`, so no database and no network are needed.

```python
# tests/test_eval_runner.py
def test_different_sql_same_rows_scores_correct():
    # stub returns valid-but-different SQL; fake executor returns identical rows
    assert result.correct is True and result.structure_differs is False


def test_structure_differs_is_reported_but_does_not_fail():
    # candidate reads player_season_club, reference reads player_season,
    # rows identical, question has no `forbidden` entry
    assert result.correct is True and result.structure_differs is True


def test_prose_answer_scores_incorrect_without_raising():
    # stub returns "I cannot answer that."
    assert result.executes is False and result.correct is False
    assert "empty" in result.reason.lower() or "not valid sql" in result.reason.lower()


def test_empty_answer_scores_incorrect_without_raising():
    # stub returns ""
    assert result.executes is False and result.correct is False


def test_provider_failure_is_infra_error_not_a_wrong_answer():
    # stub raises RuntimeError("503 Service Unavailable")
    assert result.infra_error is True and result.correct is None


def test_forbidden_minutes_filter_fails_that_dimension_only():
    # totals question, forbidden=("minutes_filter",), candidate adds the filter,
    # rows happen to match
    assert result.correct is True and result.no_forbidden is False


def test_missing_required_column_fails_that_dimension_only():
    assert result.correct is True and result.required_columns is False


def test_unanswerable_question_scores_none_for_correct():
    assert result.correct is None and result.executes is True


def test_repairs_used_is_carried_through():
    # stub returns a refused query first, then a valid one
    assert result.repairs_used == 1


def test_run_suite_calls_on_result_per_question_and_carries_flags():
    # client with temperature_supported=False
    assert len(seen) == 3 and suite.temperature_supported is False


def test_run_id_is_stable_and_model_slugged():
    assert suite.run_id == "20261116T120000Z-gemini-3.8-flash"


# --- added in review ---


def test_a_broken_reference_sql_is_reported_as_such_not_as_a_model_failure():
    # fake executor fails only for the reference SQL
    assert result.reference_failed is True and result.correct is None
    assert "reference" in result.reason.lower()


def test_failed_questions_keep_the_first_rows_of_both_sides():
    # reference returns 6 rows, candidate returns 6 different rows
    assert len(result.reference_rows) == 5 and len(result.candidate_rows) == 5


def test_green_questions_keep_no_rows():
    assert result.correct is True and result.reference_rows == ()


def test_reference_cache_executes_each_reference_once():
    cache: dict = {}
    runner.run_question(q, conn=conn, client=stub, reference_cache=cache)
    runner.run_question(q, conn=conn, client=stub, reference_cache=cache)
    assert calls["reference"] == 1 and set(cache) == {q.id}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_runner.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `runner.py`**

`run_question` order of operations, which the tests pin:
1. Call `generate.text_to_sql(question.question, conn=conn, client=client)` inside `try/except Exception` → `infra_error`.
2. If `SqlResult.ok` is false (guard refused every attempt), `executes=False`, `correct=False` (or `None` for `unanswerable`), `reason` from the last attempt's refusal.
3. Execute the candidate with `execute.run_sql`. A `psycopg` error means `executes=False`.
4. Structural dimensions from `structure.missing_required` / `structure.violated_forbidden` — these are evaluated on the generated SQL even when execution failed, so a report can still say what was wrong.
5. Correctness only when `question.scores_correctness`: fetch the reference from `reference_cache` or run it with `execute.run_sql` and store it. If the reference itself did not execute, set `reference_failed=True`, `correct=None` and a `reason` naming the gold set — a broken reference must never be charged to the model, and `correct=None` keeps it out of the denominator the same way an `infra_error` is. Otherwise `compare.compare(..., order_sensitive=question.order_sensitive)`.
6. `structure_differs` = `relations_used(candidate) != relations_used(reference)`.
7. When any of the four dimensions is not green, keep `reference_rows` and `candidate_rows` (first `ROWS_KEPT`). Green questions keep none — the rows exist to judge a disagreement, and a report that carries them for all 40 is unreadable.

`run_suite` is a loop that collects results and reads the three provider flags off the client afterwards via `getattr(client, name, default)` — a stub client need not have them.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/evals/sql/runner.py tests/test_eval_runner.py
git commit -m "feat(evals): four-dimension scoring runner for the SQL benchmark"
```

---

## Task 6: Report writer

**Files:**
- Create: `src/football_ai/evals/sql/report.py`
- Test: `tests/test_eval_report.py`

**Interfaces:**
- Consumes: `runner.SuiteResult`, `runner.QuestionResult`.
- Produces:
  ```python
  INFRA_ERROR_WARNING_RATIO = 0.10

  @dataclass(frozen=True)
  class Scores:
      scored: int            # denominator: scoring categories minus infra errors
      correct: int
      executes: int
      required_columns: int
      no_forbidden: int
      infra_errors: int
      reference_failures: int
      @property
      def accuracy(self) -> float | None    # None when scored == 0

  @dataclass(frozen=True)
  class Disagreement:
      id: str
      category: str
      question: str
      verdicts: dict[str, bool | None]   # model name -> its `correct` value
      relations: dict[str, frozenset[str]]   # model name -> relations it read

  def score(results: Sequence[QuestionResult]) -> Scores
  def by_category(suite: SuiteResult) -> dict[str, Scores]
  def disagreements(a: SuiteResult, b: SuiteResult) -> tuple[Disagreement, ...]
      # questions present in both suites whose `correct` values differ
  def to_json(suites: Sequence[SuiteResult]) -> str
  def to_markdown(suites: Sequence[SuiteResult], *, threshold: float) -> str
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_report.py
def test_unanswerable_is_excluded_from_the_denominator():
    # 4 scoring questions (3 correct) + 2 unanswerable
    assert report.score(results).scored == 4
    assert report.score(results).accuracy == pytest.approx(0.75)


def test_infra_errors_are_excluded_from_the_denominator():
    # 4 scoring questions, 1 infra_error, 2 of the remaining 3 correct
    s = report.score(results)
    assert s.scored == 3 and s.infra_errors == 1 and s.accuracy == pytest.approx(2 / 3)


def test_accuracy_is_none_when_everything_infra_errored():
    assert report.score(all_infra).accuracy is None


def test_markdown_does_not_crash_when_accuracy_is_none():
    md = report.to_markdown([all_infra_suite], threshold=0.70)
    assert "n/a" in md


def test_markdown_states_the_denominator():
    assert "36" in report.to_markdown([suite_of_40], threshold=0.70)


def test_markdown_warns_above_the_infra_error_ratio():
    assert "karşılaştırılabilir değil" in report.to_markdown([noisy_suite], threshold=0.70)


def test_markdown_reports_repair_counts_in_three_buckets():
    md = report.to_markdown([suite], threshold=0.70)
    assert "ilk denemede" in md and "onarımla" in md and "reddedilen" in md


def test_markdown_flags_dropped_parameters():
    # suite.temperature_supported is False
    assert "temperature" in report.to_markdown([suite], threshold=0.70)


def test_disagreements_lists_questions_where_verdicts_differ():
    d = report.disagreements(strong, weak)
    assert [x.id for x in d] == ["rates-02"]


def test_json_round_trips_the_generated_sql():
    payload = json.loads(report.to_json([suite]))
    assert payload["suites"][0]["results"][0]["generated_sql"] == "select 1 limit 200"


# --- added in review ---


def test_by_category_scores_each_category_separately():
    cats = report.by_category(suite)
    assert cats["totals"].accuracy == pytest.approx(1.0)
    assert cats["rates"].accuracy == pytest.approx(0.5)


def test_reference_failures_are_counted_and_excluded():
    s = report.score(results)  # 4 scoring questions, 1 reference_failed
    assert s.reference_failures == 1 and s.scored == 3


def test_markdown_names_broken_references_separately_from_model_errors():
    assert "gold set" in report.to_markdown([suite], threshold=0.70).lower()


def test_markdown_prints_both_row_sets_for_a_failed_question():
    md = report.to_markdown([suite], threshold=0.70)
    assert "beklenen" in md.lower() and "gelen" in md.lower()


def test_disagreements_ignores_questions_missing_from_one_suite():
    # the second suite was run with --only, so it has 1 of the 2 questions
    assert [x.id for x in report.disagreements(full, partial)] == ["rates-02"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_report.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `report.py`**

Markdown layout, in order: a heading with the run id, model, denominator, accuracy against the threshold, the infra-error count and the reference-failure count; the category table (one row per category, columns `n`, `correct`, `executes`, `required_columns`, `no_forbidden`); the repair buckets; the dropped-parameter note when a flag is `False`; the disagreement table when two suites were given; then a per-question appendix for everything that was not fully green, carrying the failure `reason`, the generated SQL, and the two row sets side by side under `Beklenen` / `Gelen`. Turkish headings. Accuracy renders as `n/a` when `scored == 0`. Reference failures are listed under their own heading naming the gold set as the cause, never mixed into the model's errors.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/evals/sql/report.py tests/test_eval_report.py
git commit -m "feat(evals): JSON and Markdown reporting with category breakdown"
```

---

## Task 7: The `eval-sql` CLI

**Files:**
- Create: `scripts/eval_sql.py`
- Modify: `Makefile` (`.PHONY`, help text, `eval-sql` and `eval-sql-both` recipes)
- Test: `tests/test_eval_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: `main(argv: list[str] | None = None) -> int`, importable because `pythonpath = ["scripts"]` is already set in `pyproject.toml`.

CLI surface:

```
uv run python scripts/eval_sql.py [--model M] [--models M1,M2] [--category C]
                                  [--only id,id] [--out DIR] [--threshold 0.70]
```

Writes `<out>/<run_id>.json`, `<out>/<run_id>.md` and copies the Markdown to `reports/eval_sql_latest.md`. Default `--out` is `reports/eval_sql`. Exit code 1 when the first model's accuracy is below the threshold or is `None`; 0 otherwise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_cli.py
def test_exit_code_is_one_below_threshold(tmp_path, monkeypatch):
    # monkeypatch eval_sql.run_suite to return a 50% suite
    assert eval_sql.main(["--out", str(tmp_path), "--threshold", "0.70"]) == 1


def test_exit_code_is_zero_at_threshold(tmp_path, monkeypatch):
    assert eval_sql.main(["--out", str(tmp_path), "--threshold", "0.70"]) == 0


def test_writes_json_and_markdown_named_by_run_id(tmp_path, monkeypatch):
    eval_sql.main(["--out", str(tmp_path)])
    assert (tmp_path / f"{run_id}.json").exists() and (tmp_path / f"{run_id}.md").exists()


def test_only_filter_restricts_the_questions(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        eval_sql, "run_suite", lambda qs, **kw: seen.extend(q.id for q in qs) or _fake_suite()
    )
    eval_sql.main(["--only", "totals-01,rates-01", "--out", str(tmp_path)])
    assert seen == ["totals-01", "rates-01"]


def test_unknown_only_id_is_an_error_not_an_empty_run(capsys):
    assert eval_sql.main(["--only", "nope-99"]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_eval_cli.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `scripts/eval_sql.py`**

`force_utf8()` first. `argparse` as in `scripts/ask.py`. One `db.connect(db.readonly_dsn())` for the whole run, and one `reference_cache` dict shared across every `run_suite` call so the reference queries run once regardless of how many models are evaluated. For each model, a fresh `generate.LiteLLMClient(model=...)` so the provider flags belong to that model. Progress printed per question through `on_result` — a 40-question run takes minutes and silence is indistinguishable from a hang. `--models` runs several and passes all suites to `report.to_markdown`, which then emits the disagreement table.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_eval_cli.py -v`
Expected: PASS

- [ ] **Step 5: Add the Makefile targets**

```make
eval-sql:
	$(UV) run python scripts/eval_sql.py

eval-sql-both:
	$(UV) run python scripts/eval_sql.py --models gemini/gemini-3.8-flash,gemini/gemini-3.1-flash-lite
```

Add both plus `eval-sql-gold` to `.PHONY` and to `help`.

- [ ] **Step 6: Commit**

```bash
git add scripts/eval_sql.py tests/test_eval_cli.py Makefile
git commit -m "feat(evals): make eval-sql runner with threshold exit code"
```

---

## Task 8: GitHub Actions

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: the workflow run itself

**Interfaces:** consumes `make lint`, `make test`, `scripts/migrate.py`, `make eval-sql-gold`.

- [ ] **Step 1: Write the workflow**

Three jobs on `push` and `pull_request`:

- `lint` — checkout, `astral-sh/setup-uv` with cache, `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`
- `test` — same setup, `uv run pytest` (the default `addopts` already excludes `data` and `db`)
- `gold` — `services: db: image: pgvector/pgvector:pg17` with a health check, env vars matching `.env.example` (`POSTGRES_*` and `POSTGRES_RO_*`), then `uv run python scripts/migrate.py` and `make eval-sql-gold`. **No ETL.** `EXPLAIN` validates against the schema with no rows present.

- [ ] **Step 2: Set the database environment variables directly on the job**

Resolved during review, no investigation needed: `db.load_env()` is `load_dotenv(REPO_ROOT / ".env", override=False)` (`src/football_ai/data/db.py:59`). A missing `.env` is not an error and real environment variables win, so the workflow sets `POSTGRES_*` and `POSTGRES_RO_*` as job `env:` and writes no file. `POSTGRES_RO_PASSWORD` is required — `scripts/migrate.py:48` raises without it.

Grants live in the migrations (`infra/migrations/001_schema.sql:423`, `002_...:503-508`, `003_...:216-218`), so `football_ro` can `EXPLAIN` every relation on a migrated-but-empty database. No ETL needed.

- [ ] **Step 3: Push the branch and read the run**

Run: `gh run watch` (check `gh auth status` first)
Expected: three green jobs, total under 5 minutes

- [ ] **Step 4: Verify the gold job actually catches drift**

Temporarily rename a column in one reference SQL, push, and confirm the `gold` job fails with that question's id. Revert.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint, unit tests and LLM-free gold set validation"
```

---

## Task 9: Run the benchmark and write the analysis

**Files:**
- Create: `reports/eval_sql/<run_id>.{json,md}`, `reports/eval_sql_latest.md`
- Modify: `README.md`, `DECISIONS.md`, `CLAUDE.md`, `docs/PLAN.md` status

- [ ] **Step 1: Run both models for real**

Run: `make eval-sql-both`
Expected: a completed run with `infra_error` under 10%. If the provider is saturated, switch the strong model per the `_hint` guidance and record which model was actually used.

- [ ] **Step 2: Read the per-question appendix and classify the failures**

Group every non-green question into error types (e.g. wrong relation for transfers, minutes filter on a total, missing `comparison_group_size`, invented column). The three most frequent go in the README with one example each.

- [ ] **Step 3: Write the README section**

A "Text-to-SQL doğruluğu" section: the headline accuracy with its denominator, the category table, the three error types with examples, the disagreement count between the two models, and the repair-loop numbers. State the model names and the date — a number without them is not reproducible.

- [ ] **Step 4: Write the DECISIONS entries**

`D-026` result-set equality as the judge plus the four dimensions; `D-027` CI deterministic, LLM local, `EXPLAIN` on an empty database; `D-028` threshold on the strong model, weak model as a diagnostic. Each with Bağlam / Karar / Alternatifler / Sonuç-ölçüm / Tarih, and real numbers from Step 1 in the Sonuç field.

- [ ] **Step 5: Update CLAUDE.md and the plan status**

Add a "Text-to-SQL değerlendirmesi (Gün 6)" section with the rules worth carrying forward, and tick Gün 6 in the status list with the measured accuracy.

- [ ] **Step 6: Verify the acceptance criteria and report honestly**

Run: `make check` then `make eval-sql-gold`
Expected: both green. Then state, for each Day 6 acceptance criterion, whether it was met with the number that shows it. If accuracy came in under 70%, say so plainly — the measurement stands and the prompt work is the next step, not a reason to edit the gold set.

- [ ] **Step 7: Commit**

```bash
git add README.md DECISIONS.md CLAUDE.md docs/PLAN.md reports/eval_sql
git commit -m "docs(evals): day 6 text-to-SQL benchmark results and error analysis"
```

---

## What already exists (reused, not rebuilt)

| Existing | How this plan uses it |
| --- | --- |
| `sql_agent.guard.validate` | Both sides of every comparison go through it. Only change: `_cte_names` becomes public `cte_names` so `structure` can share it. |
| `sql_agent.generate.text_to_sql` | The runner calls it unchanged. The repair loop, the `Attempt` list and `SqlResult.repairs_used` already exist for exactly this measurement. |
| `generate.LiteLLMClient` flags | `temperature_supported`, `reasoning_effort_supported`, `retries_used`, `call_log` were all added on day 5 "so day 6 can report it". The report reads them; nothing new is instrumented. |
| `sql_agent.schema.describe` + `_schema_cache` | Schema prompt generated once per process. No new caching. |
| `data.db.readonly_dsn` / `connect` | Same role and `search_path` as the agent. |
| `football_ai.metrics` loader shape | `goldset.py` copies the `parse(raw)` / `load(path)` split and the `_require` error style rather than inventing a config pattern. |
| `tests/test_sql_guard_db.py` | `ro_conn` fixture pattern. |
| `pyproject.toml` markers | `data` and `db` already exist and are already excluded by default; CI needs no new pytest configuration. |
| `console.force_utf8` | Both new scripts call it. |

Nothing here is a parallel rebuild. The one new concept is the gold set itself.

## NOT in scope (considered, deferred, with reasons)

- **Running the LLM eval in CI.** User decision. Provider 503s would make PRs red for reasons unrelated to the change.
- **Downloading OpenPlay in CI and running the ETL.** `EXPLAIN` on a migrated empty database answers the schema-drift question, which is the one CI can answer cheaply. "Are the numbers still the same" is a local question because only local has the data.
- **Repeated runs per question for variance.** Gemini 3.x rejects `temperature`, so runs are not deterministic. Measuring that variance properly means N runs per question and a confidence interval; day 6 reports one run and names the limitation. Revisit if the disagreement table turns out to be dominated by noise.
- **Prompt fixes found by this benchmark.** Day 6 builds the measurement and takes the first reading. Changing `SYSTEM_PROMPT` in the same commit series would make the first number unattributable.
- **Growing the repair loop past one attempt.** Day 6 measures whether one is enough; acting on the answer is a separate change.
- **MLflow / Langfuse tracking of eval runs.** Day 21 owns observability. JSON files on disk are enough to compare two runs.
- **Parallel LLM calls.** Free-tier rate limits make concurrency a reliability problem, and a 7-minute local run is not a bottleneck worth that risk.
- **An eval gate in CI on accuracy.** Day 20 owns that. The exit code is wired now so Day 20 does not need a wrapper.

## Failure modes per new codepath

| Codepath | Realistic production failure | Test? | Handled? | Visible to the user? |
| --- | --- | --- | --- | --- |
| `runner.run_question` → `text_to_sql` | provider 503 after all retries | yes (Task 5) | yes, `infra_error` | yes, in the report heading and the denominator |
| `runner.run_question` → candidate execute | model invents a column; Postgres errors | yes (Task 5, Task 4) | yes, `executes=False` | yes, appendix reason |
| `runner.run_question` → reference execute | the gold set's own SQL rots after a migration | yes (Task 5) | yes, `reference_failed`, excluded from the denominator | yes, its own report heading naming the gold set |
| `compare.compare` | `None` in a sort key raises `TypeError` and kills the whole run at question 23 | yes (Task 2) | yes, total-order key | would otherwise be a crash mid-run, losing 22 results |
| `compare.values_equal` | `Decimal` vs `float` judged unequal, every numeric question fails | yes (Task 2) | yes, tolerance path | would otherwise read as "accuracy 0%" and look like a prompt problem |
| `report.score` | every question infra-errored, denominator 0, `ZeroDivisionError` | yes (Task 6) | yes, `accuracy is None` → `n/a` | yes |
| `execute.run_sql` | a refused query reaches the cursor | yes (Task 4) | yes, short-circuits on `guard_refusal` | yes |
| `eval_sql.main` | `--only` with a typo runs zero questions and reports 0% | yes (Task 7) | yes, exit code 2 | yes, error message |
| CI `gold` job | a migration renames a column; every reference breaks | yes (Task 8 step 4 verifies it) | yes, job fails with the question ids | yes, red PR |

No critical gaps: every failure mode above has a test, error handling, and a visible message.

## Worktree parallelization

| Step | Modules touched | Depends on |
| --- | --- | --- |
| Task 1 goldset | `src/football_ai/evals/sql/` | — |
| Task 2 compare | `src/football_ai/evals/sql/` | — |
| Task 3 structure | `src/football_ai/evals/sql/`, `src/football_ai/sql_agent/` | — |
| Task 4 gold set + execute | `evals/`, `src/football_ai/evals/sql/`, `scripts/` | 1, 3 |
| Task 5 runner | `src/football_ai/evals/sql/` | 1, 2, 3, 4 |
| Task 6 report | `src/football_ai/evals/sql/` | 5 |
| Task 7 CLI | `scripts/`, `Makefile` | 5, 6 |
| Task 8 CI | `.github/` | 4 |
| Task 9 docs | `README.md`, `DECISIONS.md`, `reports/` | 7, 8 |

Tasks 1, 2 and 3 are independent of each other but all land in the same module directory, and everything from Task 4 on depends on their types. Sequential implementation; no parallelization opportunity worth a worktree. Task 8 could run in parallel with Task 5-7 (only `.github/` touched, depends only on Task 4) if speed mattered.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 5 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a, no UI |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

Scope: accepted as-is (13 files, but 6 are independent pure modules plus their tests; collapsing them would produce one 500-line evaluator).

Findings and resolutions:
- **[P1] Report kept no result rows** — a wrong hand-written reference would be reported as a model failure with no way to judge it from the report. Resolved: first 5 rows of both sides kept for non-green questions.
- **[P1] Gold checks duplicated across pytest and the script**, two of the six also silently needed loaded data. Resolved: the script is the single implementation of the six data-free checks; the db test calls `main()` and owns only the two data-dependent checks.
- **[P1] Gold set had no self-consistency check** — a reference SQL could fail its own `required_columns`. Resolved: checks 5 and 6 added to the script.
- **[P2] Reference SQL re-executed per model.** Resolved: `reference_cache` keyed by question id, shared across suites.
- **[P2] Two unmade decisions in the plan text** (`cte_names` sharing, `values_equal` string fallback). Resolved: `guard.cte_names` made public and imported; the string clause dropped.

Also added during review: a `reference_failed` dimension so gold-set rot is never charged to the model, 9 new test cases across Tasks 4, 5 and 6, and Task 8's open question resolved by reading `db.py:59` — `load_dotenv` tolerates a missing `.env` and real environment variables win, so CI sets job `env:` and writes no file.

Outside voice: skipped. Codex is not installed, and the fallback is a Claude subagent, which this project's instructions forbid without an explicit request.

**VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
