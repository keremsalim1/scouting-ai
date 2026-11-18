# Day 7 — `player_profile(player_id)` + Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `player_profile(conn, player_id, comp, season)`, a function returning a JSON-ready Pydantic model with per-category percentile scores (possession-adjusted for defending), plus a radar plot over the player's position-relevant categories.

**Architecture:** One new SQL migration adds a touches-share possession proxy and a per-player average-opponent-possession view. A new `src/football_ai/scouting` package reads `player_metrics`/`player_per90` (falling back to raw per-90 values for sub-threshold players), assembles the Pydantic model, and hands it to an `mplsoccer`-based radar plotter. All DB access goes through the existing `football_ro` role via `football_ai.data.db.connect`/`readonly_dsn`.

**Tech Stack:** Python 3.12, psycopg3, Pydantic (new dependency), PostgreSQL views, mplsoccer (new dependency), pytest (`db` marker for DB-backed tests).

**Spec:** [docs/superpowers/specs/2026-11-18-day7-player-profile-design.md](../specs/2026-11-18-day7-player-profile-design.md)

## Global Constraints

- `football_ro` role only for all reads; no raw-SQL string interpolation of caller input — `player_id`/`comp`/`season` are passed as psycopg query parameters, never f-string'd into SQL.
- Per-90 rule (`CLAUDE.md`): ratios are ratios of sums; a zero denominator yields NULL via `nullif`, never 0.
- `data_attribution` on the model is literally `"openplay (Noah Bair)"`.
- `min_minutes` threshold comes from `metrics.load().min_minutes` (currently 900), not hardcoded.
- Possession adjustment (`PAdj = raw_per90 × 50 / avg_opponent_possession_pct`) applies **only** to metrics with `category == "defending"`.
- Category score = simple mean of that category's non-null metric percentiles; a category with zero non-null percentiles scores `None`, not `0`.
- `discipline` category is never included in `radar_categories` for any position group.
- Acceptance (Day 7, `docs/PLAN.md:30`): profile call completes in < 1 s; `minutes_played`, `position_group`, and a comparison-scope value are present on every row, including for a player below the 900-minute threshold.

## Review Focus

- **Player below 900 minutes.** `player_metrics` omits them entirely (Day 4 behavior), so a naive `SELECT ... FROM player_metrics WHERE player_id = ...` returns zero rows and the function must not return an empty/broken profile — it must fall back to `player_per90` for raw values and set `comparison_scope = 'below_minutes_threshold'` with a non-null `sample_warning`.
- **Player with no matches in `category == 'defending'`** (e.g. a pure striker with zero tackles attempted this season) — their `defending` category must score `None`, not `0`, and must not appear in a `KeyError` or divide-by-zero in the PAdj step.
- **`avg_opponent_possession_pct` is NULL** (data gap in touches) — every `possession_adjusted_value` on `defending` metrics must come back `None` with `possession_adjustment_note` explaining why, not a crash or a silently wrong number.
- **Unknown/nonexistent `player_id`.** The function must raise a clear, specific error (not a generic `IndexError` from an empty result) so a caller (API, agent) can tell "player not found" from "DB unreachable."
- **A position group with very few radar categories (GK: `goalkeeping, passing`).** `radar_categories` must still be a valid non-empty list and `plot_radar` must not assume a fixed axis count (e.g. hardcoded 5 or 7).

---

## File Structure

- Create: `infra/migrations/004_possession.sql` — `team_match_touches`, `match_possession`, `player_possession` views; grants to `football_ro`.
- Create: `src/football_ai/scouting/__init__.py` — empty package marker.
- Create: `src/football_ai/scouting/categories.py` — `POSITION_CATEGORIES: dict[str, tuple[str, ...]]` constant (the position→category table from the spec).
- Create: `src/football_ai/scouting/calc.py` — pure functions: `category_score(percentiles: list[float | None]) -> float | None`, `possession_adjust(value: float, avg_opponent_possession_pct: float | None) -> float | None`.
- Create: `src/football_ai/scouting/profile.py` — `MetricValue`, `CategoryScore`, `PlayerProfile` Pydantic models; `PlayerNotFoundError`; `player_profile(conn, player_id, comp, season) -> PlayerProfile`.
- Create: `src/football_ai/scouting/radar.py` — `plot_radar(profile: PlayerProfile) -> matplotlib.figure.Figure`.
- Modify: `pyproject.toml` — add `pydantic` and `mplsoccer` to `dependencies`.
- Test: `tests/test_scouting_calc.py`, `tests/test_scouting_categories.py` (no DB), `tests/test_scouting_profile_db.py`, `tests/test_scouting_possession_db.py`, `tests/test_scouting_radar.py` (DB-backed tests marked `@pytest.mark.db`, same `ro_conn` fixture pattern as `tests/test_eval_gold_db.py`).

---

### Task 1: Dependencies

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `pydantic.BaseModel` available to Task 4; `mplsoccer.Radar` available to Task 5.

- [ ] **Step 1: Add `pydantic>=2.11.0` and `mplsoccer>=1.5.0` to `[project].dependencies` in `pyproject.toml`**
- [ ] **Step 2: Run `uv sync`**

Run: `uv sync`
Expected: resolves and installs both packages with no conflicts.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pydantic and mplsoccer for Day 7 player profile"
```

---

### Task 2: Possession migration

**Files:**
- Create: `infra/migrations/004_possession.sql`
- Test: `tests/test_scouting_possession_db.py`

**Interfaces:**
- Produces: `football.team_match_touches(match_id, team_id, team_touches)`, `football.match_possession(match_id, team_id, opponent_id, team_possession_pct, opponent_possession_pct)`, `football.player_possession(comp, season, player_id, avg_opponent_possession_pct)` — all granted `SELECT` to `football_ro`. Task 4 queries `football.player_possession` by `(comp, season, player_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scouting_possession_db.py
import pytest
from football_ai.data.db import connect, readonly_dsn

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    import psycopg

    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_match_possession_sums_to_100(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select team_possession_pct + opponent_possession_pct "
            "from football.match_possession limit 500"
        )
        rows = cur.fetchall()
    assert rows, "expected at least one match_possession row"
    for (total,) in rows:
        assert abs(total - 100.0) < 0.01


def test_player_possession_is_within_bounds(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select avg_opponent_possession_pct from football.player_possession "
            "where avg_opponent_possession_pct is not null limit 500"
        )
        rows = cur.fetchall()
    assert rows, "expected at least one player_possession row"
    for (pct,) in rows:
        assert 0.0 <= pct <= 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scouting_possession_db.py -v -m db`
Expected: FAIL — `relation "football.match_possession" does not exist`.

- [ ] **Step 3: Write `infra/migrations/004_possession.sql`**

Follow the SQL shapes given verbatim in the spec's "Possession proxy and PAdj" section (`team_match_touches`, `match_possession` joining a team to its opponent by shared `match_id`, `player_possession` minutes-weighting `opponent_possession_pct` by `pms.minutes_played` from `player_match_stats`). End with:

```sql
grant select on football.team_match_touches to football_ro;
grant select on football.match_possession   to football_ro;
grant select on football.player_possession  to football_ro;
```

- [ ] **Step 4: Apply the migration**

Run: `make migrate`
Expected: migration `004_possession.sql` applies with no error.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scouting_possession_db.py -v -m db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add infra/migrations/004_possession.sql tests/test_scouting_possession_db.py
git commit -m "feat(scouting): touches-share possession proxy for PAdj defending metrics"
```

---

### Task 3: Position → category map

**Files:**
- Create: `src/football_ai/scouting/__init__.py`
- Create: `src/football_ai/scouting/categories.py`
- Test: `tests/test_scouting_categories.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `POSITION_CATEGORIES: dict[str, tuple[str, ...]]`, keyed by the 8 position groups (`GK, CB, FB, DM, CM, AM, W, FW` — `CLAUDE.md`). Task 4 calls `POSITION_CATEGORIES[position_group]` to build `radar_categories`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scouting_categories.py
from football_ai.scouting.categories import POSITION_CATEGORIES

POSITION_GROUPS = {"GK", "CB", "FB", "DM", "CM", "AM", "W", "FW"}
VALID_CATEGORIES = {
    "shooting",
    "creation",
    "passing",
    "progression",
    "defending",
    "duels",
    "discipline",
    "goalkeeping",
}


def test_all_position_groups_present():
    assert set(POSITION_CATEGORIES.keys()) == POSITION_GROUPS


def test_no_category_is_discipline():
    for cats in POSITION_CATEGORIES.values():
        assert "discipline" not in cats


def test_categories_are_known_and_nonempty():
    for cats in POSITION_CATEGORIES.values():
        assert cats
        assert set(cats) <= VALID_CATEGORIES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scouting_categories.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting'`.

- [ ] **Step 3: Implement `POSITION_CATEGORIES` in `src/football_ai/scouting/categories.py`**

Use exactly the table from the spec's "Position group → radar categories" section (GK: goalkeeping, passing; CB: defending, duels, passing, progression; FB: defending, duels, passing, progression, creation; DM: defending, duels, passing, progression; CM: passing, progression, creation, defending; AM: creation, passing, shooting, progression; W: creation, shooting, duels, progression; FW: shooting, creation, duels). Values are tuples, order is display order for the radar.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scouting_categories.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/scouting/__init__.py src/football_ai/scouting/categories.py tests/test_scouting_categories.py
git commit -m "feat(scouting): position-to-radar-category map"
```

---

### Task 4: Pure calculation helpers

**Files:**
- Create: `src/football_ai/scouting/calc.py`
- Test: `tests/test_scouting_calc.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `category_score(percentiles: list[float | None]) -> float | None`, `possession_adjust(value: float, avg_opponent_possession_pct: float | None) -> float | None`. Task 5 calls both.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scouting_calc.py
from football_ai.scouting.calc import category_score, possession_adjust


def test_category_score_averages_non_null():
    assert category_score([80.0, 60.0, 40.0]) == 60.0


def test_category_score_excludes_nulls_from_average():
    assert category_score([80.0, None, 20.0]) == 50.0


def test_category_score_all_null_is_none():
    assert category_score([None, None]) is None


def test_category_score_empty_is_none():
    assert category_score([]) is None


def test_possession_adjust_applies_formula():
    # raw=2.0, opponent possession 60% -> 2.0 * 50 / 60
    assert possession_adjust(2.0, 60.0) == 2.0 * 50.0 / 60.0


def test_possession_adjust_none_when_possession_unknown():
    assert possession_adjust(2.0, None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_calc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.calc'`.

- [ ] **Step 3: Implement `category_score` and `possession_adjust` in `src/football_ai/scouting/calc.py`**

`category_score` filters `None` out, returns `None` on an empty or all-`None` input, else the arithmetic mean of what's left. `possession_adjust` returns `None` if `avg_opponent_possession_pct is None`, else `value * 50.0 / avg_opponent_possession_pct`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scouting_calc.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/scouting/calc.py tests/test_scouting_calc.py
git commit -m "feat(scouting): category score and possession-adjustment math"
```

---

### Task 5: `PlayerProfile` model and `player_profile()`

**Files:**
- Create: `src/football_ai/scouting/profile.py`
- Test: `tests/test_scouting_profile_db.py`

**Interfaces:**
- Consumes: `football_ai.data.db.connect`, `readonly_dsn` (connection); `football_ai.metrics.load()` for `min_minutes`; `football_ai.scouting.categories.POSITION_CATEGORIES`; `football_ai.scouting.calc.category_score`, `possession_adjust`.
- Produces: `MetricValue`, `CategoryScore`, `PlayerProfile` (fields exactly as in the spec's "`PlayerProfile` Pydantic model" section, plus `possession_adjustment_note: str | None` and `comparison_scope` allowing `"below_minutes_threshold"` alongside the existing `"league_position" | "position_pooled" | "insufficient"` values from Day 4); `PlayerNotFoundError(Exception)`; `player_profile(conn: psycopg.Connection, player_id: int, comp: str, season: str) -> PlayerProfile`. Task 6 consumes `PlayerProfile.radar_categories` and `PlayerProfile.categories[i].score`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scouting_profile_db.py
import time
import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn
from football_ai.scouting.profile import PlayerNotFoundError, player_profile

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


@pytest.fixture
def qualified_player_id(ro_conn):
    """A player_id with minutes_played >= 900 in some comp/season."""
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played >= 900 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no qualified player in the loaded dataset")
    return row


@pytest.fixture
def sub_threshold_player_id(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select player_id, comp, season from football.player_season "
            "where minutes_played < 900 and minutes_played > 0 limit 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no sub-threshold player in the loaded dataset")
    return row


def test_qualified_player_profile_fields_always_present(ro_conn, qualified_player_id):
    player_id, comp, season = qualified_player_id
    profile = player_profile(ro_conn, player_id, comp, season)
    assert profile.minutes_played > 0
    assert profile.position_group
    assert profile.sample_warning is None
    for cat in profile.categories:
        for metric in cat.metrics:
            assert metric.comparison_scope


def test_sub_threshold_player_still_gets_full_profile(ro_conn, sub_threshold_player_id):
    player_id, comp, season = sub_threshold_player_id
    profile = player_profile(ro_conn, player_id, comp, season)
    assert profile.minutes_played > 0
    assert profile.position_group
    assert profile.sample_warning is not None
    for cat in profile.categories:
        for metric in cat.metrics:
            assert metric.comparison_scope == "below_minutes_threshold"
            assert metric.percentile is None


def test_unknown_player_raises(ro_conn):
    with pytest.raises(PlayerNotFoundError):
        player_profile(ro_conn, -1, "Premier League", "2025/26")


def test_profile_completes_under_one_second(ro_conn, qualified_player_id):
    player_id, comp, season = qualified_player_id
    start = time.monotonic()
    player_profile(ro_conn, player_id, comp, season)
    assert time.monotonic() - start < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scouting_profile_db.py -v -m db`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.profile'`.

- [ ] **Step 3: Implement the models and `player_profile` in `src/football_ai/scouting/profile.py`**

Fields per the spec. Logic:
1. Query `football.player_season` by `(player_id, comp, season)` for identity, position, minutes, matches. Raise `PlayerNotFoundError(f"no player {player_id} in {comp} {season}")` if no row.
2. Query `football.metric_config` (or call `football_ai.metrics.load().min_minutes`) for `min_minutes_threshold`.
3. If `minutes_played >= min_minutes_threshold`: pull this player's rows from `football.player_metrics` (value, percentile, comparison_scope, comparison_comp, comparison_group_size per metric) — these already exist from Day 4. Set `sample_warning = None`.
4. Else: pull raw per-90 values from `football.player_per90` for this player (one row), and for each metric in `football_ai.metrics.load().metrics`, look up the metric's `source_column`-derived value; build a `MetricValue` with `percentile=None`, `comparison_scope="below_minutes_threshold"`. For `comparison_group_size`, query `football.player_metrics` for `count(distinct player_id)` (or reuse `comparison_group_size` from any row) among players sharing `(comp, position_group, metric)` — same group this player would compare against once qualified. Set `sample_warning` to the exact message pattern from the spec (`"minutes_played ({n}) is below the {threshold}-minute threshold used for percentile comparisons; values below are shown without a percentile."`).
5. Query `football.player_possession` for `avg_opponent_possession_pct`. If `None`, set `possession_adjustment_note` to a short explanatory string; else `None`.
6. For every metric with `category == "defending"`, set `MetricValue.possession_adjusted_value = possession_adjust(value, avg_opponent_possession_pct)`.
7. Group metrics by category, build `CategoryScore` via `category_score([m.percentile for m in cat_metrics])`.
8. `radar_categories = list(POSITION_CATEGORIES[position_group])`; `categories` includes only those in `radar_categories`, in that order.
9. `generated_at = datetime.now(UTC)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scouting_profile_db.py -v -m db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/scouting/profile.py tests/test_scouting_profile_db.py
git commit -m "feat(scouting): PlayerProfile model and player_profile() with sub-threshold fallback"
```

---

### Task 6: Radar plot

**Files:**
- Create: `src/football_ai/scouting/radar.py`
- Test: `tests/test_scouting_radar.py`

**Interfaces:**
- Consumes: `PlayerProfile` (Task 5) — `radar_categories: list[str]`, `categories: list[CategoryScore]`.
- Produces: `plot_radar(profile: PlayerProfile) -> matplotlib.figure.Figure`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scouting_radar.py
from datetime import UTC, datetime

from football_ai.scouting.profile import CategoryScore, PlayerProfile
from football_ai.scouting.radar import plot_radar


def _profile(categories, radar_categories):
    return PlayerProfile(
        player_id=1,
        player="Test Player",
        teams="Test FC",
        comp="Premier League",
        season="2025/26",
        position_group="FW",
        position_group_broad="ATT",
        position_source="starts",
        position_share=1.0,
        minutes_played=1200,
        matches=14,
        min_minutes_threshold=900,
        sample_warning=None,
        avg_opponent_possession_pct=55.0,
        radar_categories=radar_categories,
        categories=categories,
        generated_at=datetime.now(UTC),
    )


def test_plot_radar_matches_two_category_count():
    categories = [
        CategoryScore(category="shooting", score=70.0, metrics=[]),
        CategoryScore(category="creation", score=40.0, metrics=[]),
    ]
    fig = plot_radar(_profile(categories, ["shooting", "creation"]))
    assert fig is not None


def test_plot_radar_handles_null_category_score():
    categories = [
        CategoryScore(category="shooting", score=None, metrics=[]),
        CategoryScore(category="creation", score=40.0, metrics=[]),
    ]
    fig = plot_radar(_profile(categories, ["shooting", "creation"]))
    assert fig is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scouting_radar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'football_ai.scouting.radar'`.

- [ ] **Step 3: Implement `plot_radar` in `src/football_ai/scouting/radar.py`**

Build `params = profile.radar_categories`, `values = [next(c.score for c in profile.categories if c.category == cat) or 0.0 for cat in params]` (a `None` score plots as `0.0` on the chart; `CategoryScore.score` itself is untouched for any other consumer, per the spec). Use `mplsoccer.Radar` with `min_range=[0]*len(params)`, `max_range=[100]*len(params)`, axis count driven entirely by `len(params)` — no hardcoded axis count. Return the `Figure`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scouting_radar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/scouting/radar.py tests/test_scouting_radar.py
git commit -m "feat(scouting): position-scoped radar plot"
```

---

### Task 7: Full suite and documentation

**Files:**
- Modify: `CLAUDE.md` (Durum section, Day 7 row; add a short "Profil ve radar (Gün 7)" rules section mirroring the Day 3/4/5/6 style)
- Modify: `DECISIONS.md` (append `D-031` or next free number: possession proxy choice, PAdj formula, below-threshold fallback)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest` and `uv run pytest -m db`
Expected: all PASS.

- [ ] **Step 2: Update `CLAUDE.md`**

Mark Day 7 done in the Durum checklist with the measured profile latency; add the rules section stating the possession-proxy source (touches share, no DB column), the PAdj formula, the position→category exclusion of `discipline`, and the below-threshold behavior.

- [ ] **Step 3: Append a decision to `DECISIONS.md`**

`## D-031: Touches-share possession proxy and PAdj formula for defending metrics` — Context (no possession column exists), Decision (touches share + `50/opponent_possession%`), Alternatives (none tracked — only one proxy was available), Date.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md DECISIONS.md
git commit -m "docs: day 7 complete — player_profile + radar"
```

---

## Self-Review

**Spec coverage:** possession proxy/PAdj → Task 2; position→category map → Task 3; category score / PAdj math → Task 4; `PlayerProfile` model + sub-threshold fallback + `PlayerNotFoundError` → Task 5; radar plot → Task 6; docs → Task 7. All spec sections covered.

**Review Focus coverage:** sub-threshold player → Task 5 test 2; empty-defending-category player → covered by Task 4's `category_score([None, ...]) is None` plus Task 5 grouping logic (no task currently exercises a *real* player with zero defending attempts end-to-end — accepted, since Task 4's unit test already proves the aggregation is null-safe and Task 5's DB fixtures depend on what's loaded); NULL possession → Task 2 test (bounds) plus Task 5 implementation step 5 (acceptable: a dedicated unit test for `possession_adjustment_note` would need a DB row with NULL possession, which the loaded dataset may not have — flagged as a gap the implementer can close with a lightweight fake-row unit test on `profile.py`'s internal builder if one exists, otherwise accepted as covered indirectly through Task 4's `possession_adjust(value, None) is None`); unknown player_id → Task 5 test 3; GK's 2-category radar → Task 6 tests use a 2-category profile directly, which exercises the "don't hardcode axis count" requirement.

**Proportion check:** plan is single-feature, 7 tasks, each with a named test; no code bodies given except where the spec fixes the exact formula. Reasonable relative to the spec's length.
