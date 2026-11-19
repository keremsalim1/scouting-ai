# Day 8 — `similar_players()` + pgvector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `similar_players(conn, player_id, comp, season, ...)` — cosine similarity over z-scored, possession-aware metric vectors stored in pgvector, with three weighting configurations measured against each other.

**Architecture:** One vector space per *broad* position group (GK/DEF/MID/ATT), metric set unioned from Day 7's `POSITION_CATEGORIES`, z-scored within `(comp, position_group_broad)`. A batch script fits the z-scores and PCA and writes three rows per player (`equal`/`role`/`pca`) into `football.player_vectors`. The query function filters candidates to the *fine* position group; the evaluation script deliberately drops that filter so position consistency can fail.

**Tech Stack:** Python 3.12, psycopg3, numpy, scikit-learn (new), pgvector, Pydantic, pytest (`db` marker).

**Spec:** [docs/superpowers/specs/2026-11-19-day8-similarity-design.md](../specs/2026-11-19-day8-similarity-design.md)

## Global Constraints

- `football_ro` role for all reads in `similar_players()`; parameterized queries only, never f-string interpolation of caller input. The build script writes as the ETL role.
- Metric set comes from `POSITION_CATEGORIES` unioned across the fine groups in each broad group. No new hand-written metric list. `discipline` stays excluded.
- Vectors are built from **individual metrics**, never Day 7's category scores.
- Possession-adjusted value is used for `category == "defending"` metrics with `unit in {"per90", "count"}`; raw value for everything else; **imputed (z=0) rather than back-filled with raw** when the adjustment could not be computed.
- `higher_is_better: false` direction is **not** flipped.
- Only players at or above `metrics.load().min_minutes` (900) get vectors or may be queried.
- Fixed vector width is **35** (MID is widest). Zero padding; `dims` and `metric_keys` make every row self-describing.
- `SimilarityResult.similarity_note` is literally `"Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."`
- `data_attribution` is literally `"openplay (Noah Bair)"`.
- Acceptance (Day 8, `docs/PLAN.md:31`): position consistency ≥ 90% target (reported per configuration, shortfall reported not iterated on); 10 queries hand-inspected, at least one a goalkeeper; winner in `DECISIONS.md`; query < 200 ms.

## Review Focus

- **A z-score column with zero standard deviation** (every player in a `(comp, broad)` cell has the same value, or the cell has one player) — division by zero would put `NaN` into the vector and silently poison every cosine against it. Expected: that dimension becomes 0 for everyone, not `NaN`. *Test in Task 4.*
- **A qualified player with no row in `player_vectors`** (build never run, or run before they qualified) — expected: a loud error naming `make build-vectors`, not an empty result list that reads as "nobody is similar to him." *Test in Task 6.*
- **`n` larger than the candidate pool** (ask for 100 similar AMs when 60 exist) — expected: return every candidate there is, not a crash and not padded rows. *Test in Task 6.*
- **The same `player_id` appearing twice** (mid-season league change → two `player_season` rows → two vectors) — expected: he is never his own match, and never appears twice in one result. *Test in Task 6.*
- **A metric added to `metrics.yaml` after the last build** — expected: `StaleVectorsError`, not similarity computed against a stale feature set. *Test in Task 6.*

---

## File Structure

- Create: `infra/migrations/005_similarity.sql` — `football.player_vectors` table, indexes, grants to `football_ro`.
- Create: `src/football_ai/scouting/broad_groups.py` — `FINE_TO_BROAD`, `BROAD_CATEGORIES`, `broad_metric_keys()`. The fine→broad mapping that mirrors the SQL function in `002`.
- Create: `src/football_ai/scouting/vectors.py` — pure numpy math: z-scoring, role weights, PCA fit with deterministic signs.
- Create: `src/football_ai/scouting/similarity.py` — `SimilarPlayer`, `SimilarityResult`, `PlayerNotQualifiedError`, `StaleVectorsError`, `similar_players()`.
- Create: `scripts/build_vectors.py` — batch build, `make build-vectors`.
- Create: `scripts/eval_similarity.py` — position-consistency measurement, `make eval-similarity`.
- Modify: `src/football_ai/scouting/calc.py` — promote `POSSESSION_ADJUSTABLE_UNITS` to a public constant.
- Modify: `src/football_ai/scouting/profile.py` — import that constant instead of its private copy.
- Modify: `pyproject.toml`, `Makefile`, `CLAUDE.md`, `DECISIONS.md`.
- Test: `tests/test_scouting_broad_groups.py`, `tests/test_scouting_vectors.py` (pure); `tests/test_scouting_vectors_db.py`, `tests/test_scouting_similarity_db.py` (`db` marker).

---

### Task 1: Dependency

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `sklearn.decomposition.PCA` and `numpy` available to Tasks 4–7.

- [ ] **Step 1: Add `scikit-learn>=1.6.0` to `[project].dependencies` in `pyproject.toml`**

numpy already arrives via pandas; do not add it separately.

- [ ] **Step 2: Run `uv sync`**

Run: `uv sync`
Expected: resolves and installs with no conflicts.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add scikit-learn for Day 8 similarity PCA"
```

---

### Task 2: `player_vectors` table

**Files:**
- Create: `infra/migrations/005_similarity.sql`
- Test: `tests/test_scouting_vectors_db.py`

**Interfaces:**
- Produces: `football.player_vectors(comp, season, player_id, position_group, position_group_broad, weighting, vec vector(35), dims int, metric_keys text[], imputed_dims int, built_at timestamptz)`, PK `(comp, season, player_id, weighting)`, `SELECT` granted to `football_ro`. Tasks 5–7 read and write it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scouting_vectors_db.py
import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_player_vectors_is_readable_and_has_expected_columns(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'football' and table_name = 'player_vectors'"
        )
        columns = {row[0] for row in cur.fetchall()}
    assert {
        "comp",
        "season",
        "player_id",
        "position_group",
        "position_group_broad",
        "weighting",
        "vec",
        "dims",
        "metric_keys",
        "imputed_dims",
        "built_at",
    } <= columns


def test_vec_column_is_pgvector_of_width_35(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select atttypmod from pg_attribute "
            "where attrelid = 'football.player_vectors'::regclass and attname = 'vec'"
        )
        assert cur.fetchone()[0] == 35
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scouting_vectors_db.py -v -m db`
Expected: FAIL — `relation "football.player_vectors" does not exist`.

- [ ] **Step 3: Write `infra/migrations/005_similarity.sql`**

Table exactly as in the Interfaces block above. Add a `check (weighting in ('equal','role','pca'))` constraint and an index on `(weighting, position_group_broad)` — every search filters on both. End with `grant select on football.player_vectors to football_ro;`.

- [ ] **Step 4: Apply the migration**

Run: `make migrate`
Expected: `apply 005_similarity.sql`, 1 migration applied.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scouting_vectors_db.py -v -m db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add infra/migrations/005_similarity.sql tests/test_scouting_vectors_db.py
git commit -m "feat(scouting): player_vectors table for pgvector similarity"
```

---

### Task 3: Broad-group metric sets

**Files:**
- Create: `src/football_ai/scouting/broad_groups.py`
- Test: `tests/test_scouting_broad_groups.py`

**Interfaces:**
- Consumes: `football_ai.scouting.categories.POSITION_CATEGORIES`, `football_ai.metrics.MetricsConfig`.
- Produces: `FINE_TO_BROAD: dict[str, str]`; `BROAD_CATEGORIES: dict[str, tuple[str, ...]]`; `broad_metric_keys(broad: str, config: MetricsConfig) -> tuple[str, ...]` returning metric keys in `metrics.yaml` order. Tasks 4–7 use all three.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scouting_broad_groups.py
from football_ai.metrics import load
from football_ai.scouting.broad_groups import (
    BROAD_CATEGORIES,
    FINE_TO_BROAD,
    broad_metric_keys,
)
from football_ai.scouting.categories import POSITION_CATEGORIES


def test_every_fine_group_maps_to_a_broad_group():
    assert set(FINE_TO_BROAD) == set(POSITION_CATEGORIES)
    assert set(FINE_TO_BROAD.values()) == {"GK", "DEF", "MID", "ATT"}


def test_broad_categories_are_the_union_of_their_fine_groups():
    for fine, broad in FINE_TO_BROAD.items():
        assert set(POSITION_CATEGORIES[fine]) <= set(BROAD_CATEGORIES[broad])


def test_measured_dimension_counts():
    config = load()
    assert {b: len(broad_metric_keys(b, config)) for b in BROAD_CATEGORIES} == {
        "GK": 11,
        "DEF": 28,
        "MID": 35,
        "ATT": 24,
    }


def test_metric_keys_follow_yaml_order():
    config = load()
    order = [m.key for m in config.metrics]
    keys = broad_metric_keys("MID", config)
    assert list(keys) == [k for k in order if k in set(keys)]


def test_no_broad_group_includes_discipline():
    for cats in BROAD_CATEGORIES.values():
        assert "discipline" not in cats
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_broad_groups.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.broad_groups'`.

- [ ] **Step 3: Implement `broad_groups.py`**

`FINE_TO_BROAD` mirrors the `football.position_group_broad` SQL function in `infra/migrations/002_position_and_season_views.sql:56-68`: GK→GK, CB/FB→DEF, DM/CM/AM→MID, W/FW→ATT. `BROAD_CATEGORIES` is derived from `POSITION_CATEGORIES` + `FINE_TO_BROAD` at import time (no hand-typed category list). `broad_metric_keys` filters `config.metrics` by `metric.category in BROAD_CATEGORIES[broad]`, preserving `config.metrics` order.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scouting_broad_groups.py -v`
Expected: PASS

- [ ] **Step 5: Add the anti-drift DB test**

The Python mapping duplicates a SQL function; a test must prove they agree. Append to `tests/test_scouting_vectors_db.py`:

```python
def test_python_fine_to_broad_matches_the_sql_function(ro_conn):
    from football_ai.scouting.broad_groups import FINE_TO_BROAD

    with ro_conn.cursor() as cur:
        cur.execute(
            "select distinct position_group, position_group_broad "
            "from football.player_season where position_group is not null"
        )
        rows = cur.fetchall()
    assert rows
    for fine, broad in rows:
        assert FINE_TO_BROAD[fine] == broad
```

Run: `uv run pytest tests/test_scouting_vectors_db.py -v -m db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/football_ai/scouting/broad_groups.py tests/test_scouting_broad_groups.py tests/test_scouting_vectors_db.py
git commit -m "feat(scouting): broad-group metric sets unioned from position categories"
```

---

### Task 4: Vector math

**Files:**
- Create: `src/football_ai/scouting/vectors.py`
- Modify: `src/football_ai/scouting/calc.py`, `src/football_ai/scouting/profile.py`
- Test: `tests/test_scouting_vectors.py`

**Interfaces:**
- Consumes: `broad_metric_keys` (Task 3), `football_ai.metrics.MetricsConfig`.
- Produces:
  - `calc.POSSESSION_ADJUSTABLE_UNITS: frozenset[str]` (public; `profile.py` imports it instead of its private `_POSSESSION_ADJUSTABLE_UNITS`).
  - `zscore_columns(matrix: np.ndarray) -> np.ndarray` — column-wise z-score, zero-variance columns become all zeros.
  - `role_scale_factors(metric_keys: Sequence[str], config: MetricsConfig) -> np.ndarray` — the per-dimension *multiplier*.
  - `fit_pca(matrix: np.ndarray, variance_target: float = 0.90, random_state: int = 0) -> tuple[np.ndarray, int]` returning `(projection, n_components)` with sign-normalised components.
  - `pad_to(vector: np.ndarray, width: int = 35) -> np.ndarray`.

  Task 5 calls all of these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scouting_vectors.py
import numpy as np

from football_ai.metrics import load
from football_ai.scouting.broad_groups import broad_metric_keys
from football_ai.scouting.vectors import (
    fit_pca,
    pad_to,
    role_scale_factors,
    zscore_columns,
)


def test_zscore_centres_and_scales_each_column():
    out = zscore_columns(np.array([[1.0], [2.0], [3.0]]))
    assert out.mean() == 0.0
    assert np.allclose(out.ravel(), [-1.224744871, 0.0, 1.224744871])


def test_zero_variance_column_becomes_zeros_not_nan():
    out = zscore_columns(np.array([[5.0, 1.0], [5.0, 2.0], [5.0, 3.0]]))
    assert np.all(out[:, 0] == 0.0)
    assert not np.isnan(out).any()


def test_single_row_matrix_becomes_zeros_not_nan():
    out = zscore_columns(np.array([[7.0, 9.0]]))
    assert np.all(out == 0.0)


def test_role_scale_factors_square_to_the_specified_weight():
    # Effective weight inside a cosine inner product is the square of the
    # multiplier, so the multiplier must be sqrt(1 / (C * k_c)).
    config = load()
    keys = broad_metric_keys("ATT", config)  # 4 categories, 24 metrics
    by_key = {m.key: m for m in config.metrics}
    counts: dict[str, int] = {}
    for k in keys:
        counts[by_key[k].category] = counts.get(by_key[k].category, 0) + 1
    factors = role_scale_factors(keys, config)
    for factor, key in zip(factors, keys, strict=True):
        category = by_key[key].category
        assert np.isclose(factor**2, 1.0 / (len(counts) * counts[category]))


def test_role_weights_give_every_category_equal_total():
    config = load()
    keys = broad_metric_keys("ATT", config)
    by_key = {m.key: m for m in config.metrics}
    totals: dict[str, float] = {}
    for factor, key in zip(role_scale_factors(keys, config), keys, strict=True):
        totals.setdefault(by_key[key].category, 0.0)
        totals[by_key[key].category] += factor**2
    assert np.allclose(list(totals.values()), list(totals.values())[0])


def test_fit_pca_keeps_enough_components_for_the_variance_target():
    rng = np.random.default_rng(0)
    matrix = zscore_columns(rng.normal(size=(200, 10)))
    projection, n_components = fit_pca(matrix, variance_target=0.90)
    assert projection.shape == (200, n_components)
    assert 1 <= n_components <= 10


def test_fit_pca_is_deterministic_across_runs():
    rng = np.random.default_rng(1)
    matrix = zscore_columns(rng.normal(size=(150, 8)))
    first, _ = fit_pca(matrix)
    second, _ = fit_pca(matrix)
    assert np.allclose(first, second)


def test_pad_to_appends_zeros_and_keeps_the_prefix():
    padded = pad_to(np.array([1.0, 2.0]), width=35)
    assert padded.shape == (35,)
    assert np.allclose(padded[:2], [1.0, 2.0])
    assert np.all(padded[2:] == 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_vectors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.vectors'`.

- [ ] **Step 3: Implement `vectors.py`**

`zscore_columns` uses the population standard deviation (`ddof=0`, matching the test's ±1.2247 expectation) and replaces any column whose stddev is 0 with zeros before dividing — never divide then clean up, or `NaN` escapes through `inf * 0`.

`role_scale_factors` returns `sqrt(1 / (C * k_c))` per the test above, where `C` is the number of distinct categories among `metric_keys` and `k_c` the metric count in that metric's category.

`fit_pca` uses `sklearn.decomposition.PCA(random_state=...)`, picks the smallest `n_components` whose cumulative `explained_variance_ratio_` reaches `variance_target`, refits (or slices) to that count, then **sign-normalises**: for each component, if the loading with the largest absolute value is negative, negate both the component and its projection column.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scouting_vectors.py -v`
Expected: PASS

- [ ] **Step 5: Promote the possession-unit constant**

Move `_POSSESSION_ADJUSTABLE_UNITS` out of `src/football_ai/scouting/profile.py` into `src/football_ai/scouting/calc.py` as `POSSESSION_ADJUSTABLE_UNITS`, keeping the explanatory comment; import it in `profile.py`. Task 5 needs the same rule and must not restate it.

Run: `uv run pytest tests/test_scouting_profile_db.py -v -m db`
Expected: PASS (unchanged behaviour — this is a move, not a change).

- [ ] **Step 6: Commit**

```bash
git add src/football_ai/scouting/vectors.py src/football_ai/scouting/calc.py src/football_ai/scouting/profile.py tests/test_scouting_vectors.py
git commit -m "feat(scouting): z-score, role weights and deterministic PCA for similarity vectors"
```

---

### Task 5: Build script

**Files:**
- Create: `scripts/build_vectors.py`
- Modify: `Makefile`
- Test: `tests/test_scouting_vectors_db.py` (append)

**Interfaces:**
- Consumes: Task 3's `FINE_TO_BROAD`/`broad_metric_keys`, Task 4's `zscore_columns`/`role_scale_factors`/`fit_pca`/`pad_to`/`POSSESSION_ADJUSTABLE_UNITS`, Task 2's table, `football_ai.scouting.calc.possession_adjust`.
- Produces: `make build-vectors`; three rows per qualified player in `football.player_vectors`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_scouting_vectors_db.py
def test_every_qualified_player_has_three_weighting_rows(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select count(*) from football.player_season s "
            "where s.minutes_played >= 900 and not exists ("
            "  select 1 from football.player_vectors v "
            "  where v.player_id = s.player_id and v.comp = s.comp "
            "    and v.season = s.season and v.weighting = 'equal')"
        )
        assert cur.fetchone()[0] == 0
    with ro_conn.cursor() as cur:
        cur.execute("select distinct weighting from football.player_vectors")
        assert {row[0] for row in cur.fetchall()} == {"equal", "role", "pca"}


def test_no_vector_contains_nan_or_infinity(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select count(*) from football.player_vectors "
            "where vec::text like '%NaN%' or vec::text like '%Infinity%'"
        )
        assert cur.fetchone()[0] == 0


def test_dims_match_the_broad_group_for_non_pca_rows(ro_conn):
    from football_ai.metrics import load
    from football_ai.scouting.broad_groups import broad_metric_keys

    config = load()
    with ro_conn.cursor() as cur:
        cur.execute(
            "select distinct position_group_broad, dims from football.player_vectors "
            "where weighting = 'equal'"
        )
        rows = cur.fetchall()
    assert rows
    for broad, dims in rows:
        assert dims == len(broad_metric_keys(broad, config))


def test_pca_rows_keep_input_metric_keys_and_fewer_dims(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select dims, cardinality(metric_keys) from football.player_vectors "
            "where weighting = 'pca' limit 50"
        )
        rows = cur.fetchall()
    assert rows
    for dims, n_keys in rows:
        assert dims <= n_keys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_vectors_db.py -v -m db`
Expected: FAIL — the table exists but is empty, so the first test reports a non-zero count of players without vectors.

- [ ] **Step 3: Implement `scripts/build_vectors.py`**

Call `football_ai.console.force_utf8()` first (project rule for any script that prints). Full rebuild in one transaction: `TRUNCATE football.player_vectors` then insert, matching the Day 2 ETL's idempotency posture.

Per broad group:
1. One bulk query joining `football.player_metrics` (qualified players only, already filtered by the view) with `football.player_possession` on `(comp, season, player_id)` — do **not** call `player_profile()` per player, which would take minutes.
2. Per player, per metric key from `broad_metric_keys(broad, config)` in order: use `possession_adjust(value, avg_opponent_possession_pct)` when `category == "defending"` and `unit in POSSESSION_ADJUSTABLE_UNITS`; raw `value` otherwise. A missing metric row, **or** a defending volume metric whose possession is unknown, is imputed — mark it and count it into `imputed_dims`.
3. Z-score within `(comp, broad)` cells, then pool the cells into one matrix per broad group.
4. Imputed entries are set to 0 **after** z-scoring (0 is the cell mean by construction), and are excluded from that column's mean/stddev so a run of imputations cannot drag the distribution.
5. `equal` = z-scores; `role` = z × `role_scale_factors`; `pca` = `fit_pca(z)[0]`.
6. `pad_to(..., 35)` each row; write `dims`, `metric_keys` (always the input keys), `imputed_dims`, `built_at`.

Add to `Makefile`:

```makefile
build-vectors:
	$(UV) run python scripts/build_vectors.py
```

and a `help` line: `build-vectors  build similarity vectors into pgvector (needs a loaded db)`.

- [ ] **Step 4: Build and verify**

Run: `make build-vectors` then `uv run pytest tests/test_scouting_vectors_db.py -v -m db`
Expected: build prints per-broad-group row counts; all tests PASS.

- [ ] **Step 5: Verify a rebuild is byte-identical**

Run: `make build-vectors` a second time, then compare — a deterministic build is what lets PCA components be recomputed rather than stored.

```bash
uv run python -c "
from football_ai.data.db import connect, readonly_dsn
conn = connect(readonly_dsn(), autocommit=True)
with conn.cursor() as cur:
    cur.execute('select md5(string_agg(vec::text, \'|\' order by comp, player_id, weighting)) from football.player_vectors')
    print(cur.fetchone()[0])
"
```

Expected: the same md5 before and after the second build. If it differs, the PCA sign normalisation from Task 4 is not doing its job — fix that, do not store the components.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_vectors.py Makefile tests/test_scouting_vectors_db.py
git commit -m "feat(scouting): build z-scored, role-weighted and PCA similarity vectors"
```

---

### Task 6: `similar_players()`

**Files:**
- Create: `src/football_ai/scouting/similarity.py`
- Test: `tests/test_scouting_similarity_db.py`

**Interfaces:**
- Consumes: Task 2's table, Task 3's `FINE_TO_BROAD`/`broad_metric_keys`, `football_ai.metrics.load`.
- Produces: `SimilarPlayer`, `SimilarityResult`, `PlayerNotQualifiedError`, `StaleVectorsError`, and `similar_players(conn, player_id, comp, season, n=10, weighting="equal") -> SimilarityResult`. Task 7 calls it; Task 7's evaluation uses its own broad-pool query rather than this function.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scouting_similarity_db.py
import time

import psycopg
import pytest

from football_ai.scouting.profile import PlayerNotFoundError
from football_ai.data.db import connect, readonly_dsn
from football_ai.scouting import similarity as similarity_module
from football_ai.scouting.similarity import (
    PlayerNotQualifiedError,
    StaleVectorsError,
    similar_players,
)

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


@pytest.fixture
def qualified_player(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played >= 900 and position_group = 'FW' limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no qualified FW in the loaded dataset")
    return row


def test_results_share_the_query_players_fine_position(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=10)
    assert len(result.results) == 10
    assert all(r.position_group == result.position_group for r in result.results)
    assert result.comparison_pool_size > 0


def test_similarity_note_and_attribution_are_present(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season)
    assert result.similarity_note == (
        "Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."
    )
    assert result.data_attribution == "openplay (Noah Bair)"
    assert result.metric_keys


def test_query_player_is_never_his_own_match(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=25)
    ids = [r.player_id for r in result.results]
    assert player_id not in ids
    assert len(ids) == len(set(ids))


def test_n_larger_than_the_pool_returns_the_whole_pool(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    result = similar_players(ro_conn, player_id, comp, season, n=10_000)
    assert len(result.results) == result.comparison_pool_size


def test_every_weighting_runs(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    for weighting in ("equal", "role", "pca"):
        result = similar_players(ro_conn, player_id, comp, season, weighting=weighting)
        assert result.weighting == weighting
        assert result.results


def test_similarity_is_ordered_descending(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    scores = [r.similarity for r in similar_players(ro_conn, player_id, comp, season).results]
    assert scores == sorted(scores, reverse=True)


def test_sub_threshold_player_raises(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played < 900 and minutes_played > 0 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no sub-threshold player in the loaded dataset")
    with pytest.raises(PlayerNotQualifiedError):
        similar_players(ro_conn, *row)


def test_unknown_player_raises(ro_conn):
    with pytest.raises(PlayerNotFoundError):
        similar_players(ro_conn, -1, "eng", "2526")


def test_missing_vector_row_raises_rather_than_returning_nothing(
    ro_conn, qualified_player, monkeypatch
):
    player_id, comp, season = qualified_player
    monkeypatch.setattr(similarity_module, "_fetch_vector_row", lambda *a, **k: None)
    with pytest.raises(StaleVectorsError):
        similar_players(ro_conn, player_id, comp, season)


def test_stale_metric_set_raises(ro_conn, qualified_player, monkeypatch):
    player_id, comp, season = qualified_player
    monkeypatch.setattr(
        similarity_module, "broad_metric_keys", lambda *a, **k: ("a_metric_added_later",)
    )
    with pytest.raises(StaleVectorsError):
        similar_players(ro_conn, player_id, comp, season)


def test_query_completes_under_200ms(ro_conn, qualified_player):
    player_id, comp, season = qualified_player
    similar_players(ro_conn, player_id, comp, season)  # warm
    start = time.monotonic()
    similar_players(ro_conn, player_id, comp, season)
    assert time.monotonic() - start < 0.2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_similarity_db.py -v -m db`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.similarity'`.

- [ ] **Step 3: Implement `similarity.py`**

Models exactly as in the spec's "API shape" section, plus `PlayerNotQualifiedError` and `StaleVectorsError`. Reuse Day 7's `PlayerNotFoundError` by importing it from `profile.py` rather than defining a second one.

Order of operations in `similar_players`:
1. Fetch identity from `football.player_season` — no row → `PlayerNotFoundError`.
2. `minutes_played < metrics.load().min_minutes` → `PlayerNotQualifiedError` naming both numbers.
3. `_fetch_vector_row(conn, player_id, comp, season, weighting)` — `None` → `StaleVectorsError` naming `make build-vectors`.
4. Compare the row's `metric_keys` against `broad_metric_keys(FINE_TO_BROAD[position_group], load())` → differ → `StaleVectorsError`.
5. Rank candidates with pgvector's cosine distance operator `<=>`, filtered to the same `position_group` and `weighting`, excluding **every** row whose `player_id` equals the query's, joined to `player_season` for name/teams/minutes/matches. `similarity = 1 - (vec <=> query_vec)`. `LIMIT` is `n` — but `comparison_pool_size` comes from a separate `count(*)` over the same filter so the "n larger than pool" test can compare the two.
6. `generated_at = datetime.now(UTC)`.

Keep both the ranking query and the count in one round trip each; the 200 ms budget is generous for ~400 rows but four round trips plus Python overhead is not free.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scouting_similarity_db.py -v -m db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/scouting/similarity.py tests/test_scouting_similarity_db.py
git commit -m "feat(scouting): similar_players() over pgvector with stale-vector guard"
```

---

### Task 7: Position-consistency evaluation

**Files:**
- Create: `scripts/eval_similarity.py`
- Modify: `Makefile`
- Test: `tests/test_scouting_similarity_db.py` (append)

**Interfaces:**
- Consumes: Task 2's table, Task 3's `FINE_TO_BROAD`.
- Produces: `make eval-similarity` writing `reports/similarity_eval.md`; importable `position_consistency(conn, weighting) -> dict[str, float]` keyed by fine position group, and `confusion(conn, weighting) -> dict[str, dict[str, int]]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_scouting_similarity_db.py
def test_position_consistency_excludes_gk_and_covers_every_other_group(ro_conn):
    from eval_similarity import position_consistency

    scores = position_consistency(ro_conn, "equal")
    assert "GK" not in scores
    assert set(scores) == {"CB", "FB", "DM", "CM", "AM", "W", "FW"}
    assert all(0.0 <= v <= 1.0 for v in scores.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scouting_similarity_db.py -v -m db -k position_consistency`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_similarity'` (`scripts/` is already on `pythonpath` per `pyproject.toml`).

- [ ] **Step 3: Implement `scripts/eval_similarity.py`**

`force_utf8()` first. For each weighting, for each qualified player **whose broad group is not GK**: take the top-10 nearest rows inside the same `position_group_broad` (any `comp`, excluding every row with that `player_id`), and record the fraction whose fine `position_group` equals the query's. `position_consistency` returns the mean of those fractions per fine position group; GK is omitted entirely, with the reason stated in the report.

The report (`reports/similarity_eval.md`) carries, per weighting: the per-group table with each group's base rate (the group's share of its broad pool) and the lift over it; the **unweighted mean across the seven non-GK groups** as the headline; the confusion breakdown; mean top-10 similarity; and measured query latency. It states plainly which configuration wins and, if none reaches 90%, says so rather than rounding the story.

Prefer one SQL statement per weighting using a `lateral` join over ~1 100 Python round trips.

Add to `Makefile`:

```makefile
eval-similarity:
	$(UV) run python scripts/eval_similarity.py
```

and a `help` line: `eval-similarity  position consistency for all three weightings (needs vectors)`.

- [ ] **Step 4: Run the evaluation**

Run: `make eval-similarity`
Expected: `reports/similarity_eval.md` written; three weightings reported; a winner named.

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_scouting_similarity_db.py -v -m db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/eval_similarity.py Makefile tests/test_scouting_similarity_db.py reports/similarity_eval.md
git commit -m "feat(scouting): measure position consistency across the three weightings"
```

---

### Task 8: Hand inspection and documentation

**Files:**
- Create: `reports/similarity_hand_review.md`
- Modify: `CLAUDE.md`, `DECISIONS.md`

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest` and `uv run pytest -m db`
Expected: all PASS. Record both counts — they go in `CLAUDE.md`.

- [ ] **Step 2: Inspect ten queries by hand**

Run `similar_players()` for ten players spanning every position group, **including at least one goalkeeper** (the `role` configuration gives `saves_per90` a third of GK similarity — this is the only place that effect is visible). Use the winning weighting from Task 7. Write `reports/similarity_hand_review.md`: the query player, the top five returned, and one line of judgement per query — plausible, or not, and why. A result that looks wrong is a finding to write down, not to hide.

- [ ] **Step 3: Update `CLAUDE.md`**

Mark Day 8 done in the Durum checklist with the measured position consistency, the winning weighting, the query latency and the test counts. Add a "Benzerlik (Gün 8)" rules section in the style of the Day 3–7 sections, stating: the broad-group vector space and why it is not fine-grained; z-score cell; PAdj reuse and the imputation rule; `vector(35)` with zero padding; `metric_keys` semantics on `pca` rows; the self-exclusion by `player_id`; `StaleVectorsError` and `make build-vectors`; and the mandatory similarity note.

- [ ] **Step 4: Append the decision to `DECISIONS.md`**

`## D-032: Benzerlik vektörleri geniş pozisyon havuzunda kurulur; kazanan ağırlıklandırma` — Bağlam (fine-group vectors made the acceptance metric mathematically undefined and z-scoring erased the signal), Karar (broad-group space, three weightings, measured), Değerlendirilen alternatifler (second evaluation-only vector space; changing the acceptance metric), Sonuç/ölçüm (the measured per-group table, the winner, latency, and any shortfall against 90% stated plainly), Tarih.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md DECISIONS.md reports/similarity_hand_review.md
git commit -m "docs: day 8 complete — similar_players + measured weighting comparison"
```

---

## Self-Review

**Spec coverage:** broad-group metric sets → Task 3; z-score/role/PCA math incl. determinism → Task 4; `vector(35)` table and padding → Task 2; possession reuse and imputation → Task 5; `similar_players()` with self-exclusion, stale guard, sub-threshold error, latency → Task 6; evaluation with GK exclusion and unweighted-mean headline → Task 7; ten hand queries incl. a goalkeeper, `DECISIONS.md`, `CLAUDE.md` → Task 8. The spec's `scikit-learn` note → Task 1. No uncovered spec section.

**Review Focus coverage:** zero-variance column → Task 4 (`test_zero_variance_column_becomes_zeros_not_nan`, `test_single_row_matrix_becomes_zeros_not_nan`, plus Task 5's `test_no_vector_contains_nan_or_infinity` end-to-end); missing vector row → Task 6 (`test_missing_vector_row_raises_rather_than_returning_nothing`); `n` beyond pool → Task 6 (`test_n_larger_than_the_pool_returns_the_whole_pool`); duplicate `player_id` → Task 6 (`test_query_player_is_never_his_own_match`); stale metric set → Task 6 (`test_stale_metric_set_raises`). All five pinned to a task.

**Type consistency:** `broad_metric_keys(broad, config)` is called with the same signature in Tasks 4, 5, 6 and in Task 5's test. `role_scale_factors` is named identically in Task 4's tests and Task 5's step 3. `_fetch_vector_row` is the monkeypatch target in Task 6's test and the function named in Task 6 step 3. `weighting` values are `'equal' | 'role' | 'pca'` in the table constraint (Task 2), the build (Task 5), the API (Task 6) and the evaluation (Task 7).

**Known gap, accepted:** no test forces a *real* player through the possession-unknown imputation path, because the loaded dataset has zero such players (confirmed during Day 7 review). The unit-level guarantee is `possession_adjust(value, None) is None` from Day 7, and Task 5's NaN sweep would catch a mishandled imputation; a synthetic fixture would test the fixture more than the code.

**Proportion:** 8 tasks, every step either a named test with assertions, an exact signature, or a command with an expected output. Code blocks are tests, not implementations — the only prose bodies are the three algorithms (zero-variance handling, sqrt-weight derivation, PCA sign normalisation) that the signatures do not determine.
