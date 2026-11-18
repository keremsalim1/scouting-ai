# Day 7 — `player_profile(player_id)` + radar: design

## Intent and why

Day 7 (`docs/PLAN.md` row 30) is the first step of Week 2 ("Profiller,
benzerlik, bilgi tabanı, API/UI"). Everything downstream — similarity
(Day 8), the API (Day 12), and later the agent's scouting reports — reads
a player through this function. It has to return a complete, self-
describing profile: raw values, percentiles, and the context needed to
judge them (minutes, sample size, comparison scope), per the scouting
rules in `CLAUDE.md` ("LLM sayı üretmez" — every number in a report must
be traceable to a tool/DB call, and the mandatory-fields list: position
group, minutes, matches, min-minutes threshold, sample warning, data
coverage, comparison group size).

Day 7's acceptance criterion is narrow and must hold exactly: **profile
returns in < 1 s; minutes, position, and comparison scope are always
present** — including for a player below the 900-minute percentile
threshold, who still gets a profile (with a sample warning), not an
error. This mirrors the project's data-quality policy: degrade and
report, never silently drop.

## Goals

- A Python function `player_profile(player_id: int, comp: str,
  season: str) -> PlayerProfile` returning a Pydantic model, built from
  `football_ro`-role DB reads only (no LLM, no computed numbers outside
  SQL/pandas).
- The model is JSON-serializable as-is for the future `/players/{id}/profile`
  API endpoint (Day 12) — no API-specific reshaping later.
- A radar-ready structure: per-category scores (0–100, simple average of
  that category's metric percentiles), restricted to the categories
  relevant to the player's position group, `discipline` always excluded.
- Possession-adjusted (PAdj) defensive metrics: `category = 'defending'`
  metrics get a second, corrected per-90 value alongside the raw one,
  using `PAdj = raw_per90 × 50 / avg_opponent_possession_pct`, where
  `avg_opponent_possession_pct` is the player's minutes-weighted average
  of opponent possession share across the matches they played (possession
  proxy: team touches share of total match touches — no possession
  column exists in the schema).
- A `radar(profile: PlayerProfile)` plotting function (mplsoccer, per
  `CLAUDE.md`'s stack) producing one radar chart scoped to the player's
  position-relevant categories.

## Non-goals

- Similarity, PCA, z-scores — Day 8.
- The FastAPI endpoint itself — Day 12. This only has to produce a model
  shaped for it.
- Possession adjustment for anything other than the `defending` category
  (not `duels`, not shooting/creation/passing/progression). The user
  confirmed the target is specifically defensive actions.
- Handling multi-club, multi-league players beyond what `player_season`
  already does (it aggregates clubs within a comp+season; cross-league
  transfers are two separate rows, which is existing, accepted behavior
  per D-014–017).

## Anti-goals (would be a failure even if it technically runs)

- Returning a profile that goes silent on sample size — a <900-minute
  player must still get `minutes_played`, `matches`, and an explicit
  `sample_warning`, never a null-filled or missing-field response.
- A PAdj number presented without the raw number next to it, or without
  stating it's possession-adjusted — the scouting rules require every
  number's provenance to be legible in the output, not just in code
  comments.
- Hardcoding the position→category map or the category list somewhere
  that drifts from `config/metrics.yaml`'s `category` field. The map
  (below) is new config, but the categories it references must come from
  the yaml's existing values, not be re-typed as strings in Python.

## Constraints

- `football_ro` role only; no raw-SQL string interpolation of user input
  (player_id is an int from an internal caller here, not an LLM-produced
  query, so the sqlglot guard from Day 5 does not apply — this is a
  direct, parameterized psycopg call).
- Per-90 rate rule from `CLAUDE.md`: ratios are ratios of sums, minutes
  filter applies to rate metrics, not to the player's eligibility for a
  profile at all.
- `float32 → double precision` widening, `nullif`-based null division,
  and the `count(*) over w` ordered-window trap all apply again if new
  aggregation SQL is written (the possession views will aggregate across
  matches).
- Must attribute data: "openplay (Noah Bair)" field on the model, as
  with every other report-shaped output in this project.

## Decided design

### Possession proxy and PAdj (new migration `004_possession.sql`)

No `possession` column exists anywhere in the schema (checked
`player_match_stats`, `matches`, `passes`, `shots` — none carry it). The
proxy is touches share, aggregated from `player_match_stats`, which
already has `touches` per player per match:

```sql
-- team_match_touches: one row per team per match
select match_id, team_id, sum(touches)::double precision as team_touches
from football.player_match_stats
group by match_id, team_id;

-- match_possession: one row per team per match, with the opponent's
-- share as the number a PAdj calc actually needs
select
    a.match_id, a.team_id, a.opponent_id,
    a.team_touches / nullif(a.team_touches + b.team_touches, 0) * 100
        as team_possession_pct,
    b.team_touches / nullif(a.team_touches + b.team_touches, 0) * 100
        as opponent_possession_pct
from team_match_touches a
join team_match_touches b on b.match_id = a.match_id and b.team_id <> a.team_id;
```

Then a per-player-season view, minutes-weighted across the matches they
actually played (from `player_match_stats`, joined to `match_possession`
on `match_id, team_id`):

```sql
select
    pms.comp, pms.season, pms.player_id,
    sum(mp.opponent_possession_pct * pms.minutes_played)
        / nullif(sum(pms.minutes_played), 0) as avg_opponent_possession_pct
from football.player_match_stats pms
join match_possession mp
  on mp.match_id = pms.match_id and mp.team_id = pms.team_id
group by pms.comp, pms.season, pms.player_id;
```

`avg_opponent_possession_pct` can be NULL if touches are missing for a
player's matches (data-quality gap, not expected given Day 1's 100%
coverage finding, but the nullif chain already protects it). When NULL,
PAdj values are omitted and a flag notes it — same "degrade and report"
pattern as everything else.

PAdj is applied in Python (not SQL) at profile-build time: for every
metric row where `category == 'defending'`, compute
`padj_value = value * 50.0 / avg_opponent_possession_pct` if the player's
`avg_opponent_possession_pct` is known, else leave `padj_value = None`.

### Position group → radar categories (new config, not yaml — see "left to the builder")

`metrics.yaml` categories, `discipline` excluded: `shooting, creation,
passing, progression, defending, duels, goalkeeping` (7 usable).
Default map (my call, football-logic default — flagged below for the
human partner to skim):

| position_group | categories |
|---|---|
| GK | goalkeeping, passing |
| CB | defending, duels, passing, progression |
| FB | defending, duels, passing, progression, creation |
| DM | defending, duels, passing, progression |
| CM | passing, progression, creation, defending |
| AM | creation, passing, shooting, progression |
| W | creation, shooting, duels, progression |
| FW | shooting, creation, duels |

Category score = simple average of that category's metric percentiles
(metrics with `percentile = null`, i.e. `comparison_scope = 'insufficient'`,
are excluded from the average rather than treated as 0; if *all* of a
category's metrics are null, the category score is null, not 0).

### `PlayerProfile` Pydantic model (new module `src/football_ai/scouting/profile.py`)

```python
class MetricValue(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    higher_is_better: bool
    percentile: float | None
    comparison_scope: str
    comparison_comp: str | None
    comparison_group_size: int
    possession_adjusted_value: float | None = None  # only set for category == "defending"


class CategoryScore(BaseModel):
    category: str
    score: float | None  # simple avg of percentiles, null-excluded
    metrics: list[MetricValue]


class PlayerProfile(BaseModel):
    player_id: int
    player: str
    teams: str
    comp: str
    season: str
    position_group: str
    position_group_broad: str
    position_source: str
    position_share: float
    minutes_played: int
    matches: int
    min_minutes_threshold: int
    sample_warning: str | None  # set when minutes_played < min_minutes_threshold
    avg_opponent_possession_pct: float | None
    radar_categories: list[str]  # the position's category list, in display order
    categories: list[CategoryScore]
    data_attribution: str = "openplay (Noah Bair)"
    generated_at: datetime
```

A player below `min_minutes_threshold` still gets this full shape:
`categories` will mostly carry `percentile = null` /
`comparison_scope = 'insufficient'` per metric (today's `player_metrics`
view already omits such players entirely, so the function falls back to
`player_per90` directly for their raw values when they're missing from
`player_metrics`, and fills percentile fields with null + the
`'insufficient'`/`'below_threshold'` scope). `sample_warning` text, e.g.:
`"minutes_played (420) is below the 900-minute threshold used for
percentile comparisons; values below are shown without a percentile."`

### Radar function

`src/football_ai/scouting/radar.py`: `plot_radar(profile: PlayerProfile)
-> matplotlib.figure.Figure` using `mplsoccer.Radar`, axes =
`profile.radar_categories`, values = each category's `score` (0 if a
whole category is null — the plot can't draw a gap, but the returned
`PlayerProfile.categories[i].score` stays `None` for any API/report
consumer that needs to know).

## Resolved gaps (builder-check round, my call)

- **`comparison_scope` for a sub-900-minute player:** a new value,
  `'below_minutes_threshold'`, distinct from the existing
  `'insufficient'` (which means "group too small," not "this player
  doesn't qualify"). Conflating them would make Day 8 unable to tell
  the two failure modes apart later.
- **`comparison_group_size` for a sub-threshold player:** still computed
  and non-null. The group size describes the *comparison group* (other
  qualified players in that comp+position+metric), not this player's
  eligibility — so it's queried the same way regardless of whether this
  player clears the threshold. `MetricValue.comparison_group_size` stays
  non-nullable `int`.
- **Radar axis count varies by position (GK: 2 categories, FB: 5):** in
  scope for Day 7, a single-player radar. Cross-player radar comparison
  (same axes for two players) is Day 8's problem if/when it needs it,
  not solved here.
- **Possession data missing (`avg_opponent_possession_pct is None`):**
  a new field, `PlayerProfile.possession_adjustment_note: str | None`,
  set to explain why `possession_adjusted_value` is null on every
  defending metric when this happens. Kept separate from
  `sample_warning`, which is specifically about the minutes threshold.

## What's left to the builder

- Exact file/module layout beyond what's named above (e.g. whether DB
  access goes through an existing `db.py` helper — check
  `src/football_ai/sql_agent` or wherever Day 5/6 connects as
  `football_ro` and reuse it rather than opening a new connection path).
- Test strategy: unit tests for the category-average and PAdj math
  against fixed numbers, plus a DB-backed test (per the `test-db` /
  `test-data` split already in the Makefile) asserting the <1s timing
  and the always-present fields for both a qualified and a
  sub-threshold player.
- Whether `avg_opponent_possession_pct` lives in a new view
  (`football.player_possession`) or is computed inline in the Python
  query — either is fine; a view matches the project's existing pattern
  of pushing aggregation into SQL (D-018 etc.) and is the default choice
  unless the builder finds a reason not to.
- The position→category table's exact storage (Python dict constant vs.
  a small YAML next to `metrics.yaml`) — a Python constant is enough
  here since it doesn't need the yaml's validation/test machinery that
  `metrics.yaml` has; promote it later only if it grows.
