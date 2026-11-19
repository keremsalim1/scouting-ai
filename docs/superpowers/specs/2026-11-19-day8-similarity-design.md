# Day 8 — `similar_players()`: design

## Intent and why

Day 8 (`docs/PLAN.md` row 31) turns the per-player snapshot built on Day 7
into a comparison engine. A scout's real question is rarely "how good is
this player" — it is "who else plays like this, and can I afford him."
Everything after this day leans on it: the agent's scouting reports
(Week 3) cite similar profiles, and `CLAUDE.md`'s mandatory report fields
already list "benzer profiller" as a required section.

The hard rule this feature exists under, from `CLAUDE.md`, is that
similarity is **not** a quality ranking: every result carries the note
**"Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."**
The design choices below (z-scoring within league, cosine on the z-scored
pattern rather than raw magnitude) are what make that note true rather
than decorative — two players match when their *shape* relative to their
own league matches, not when they are both good.

## Goals

- `similar_players(conn, player_id, comp, season, n=10, weighting=...)`
  returning a Pydantic model (API-ready, same posture as Day 7's
  `PlayerProfile`), searching **within the same fine position group**
  across all three leagues.
- Position-aware feature vectors persisted in **pgvector** (the
  extension is already enabled in `001_schema.sql`, explicitly "needed
  from day 8"): one vector space per broad group, search filtered to the
  fine group.
- Three weighting configurations, measured against each other, winner
  recorded in `DECISIONS.md`:
  - **equal** — every metric is one dimension, equally weighted.
  - **role** — every *category* carries equal total weight, split among
    its metrics, so a 7-metric category does not outvote a 3-metric one.
  - **pca** — components fitted on the z-scored matrix per broad group,
    similarity computed in component space.
- A measured **position-consistency** number per configuration (see
  "Evaluation" — this is the acceptance metric and it is deliberately
  measured without the position filter).
- 10 queries inspected by hand and written up.
- Query latency < 200 ms.

## Non-goals

- Cross-position similarity as a *product* feature. The user was explicit:
  the question is "find me other FWs like this FW." The broad-pool search
  exists only as an evaluation instrument (below), not as an API surface.
- Transfer-market value, quality ranking, or any "who is better" output.
  Explicitly forbidden by the similarity rule.
- Similarity for players below `min_minutes` (900). A per-90 rate from
  200 minutes is noise; presenting a "most similar players" list built
  on noise is exactly the silent-wrongness the project's data policy
  forbids. These players raise a specific, explanatory error — which is
  reporting, not silent dropping.
- Re-deriving the per-position metric set. `POSITION_CATEGORIES` from
  Day 7 is the single source of truth; a second list would drift.

## Anti-goals (failure even if it runs)

- A result set that reads as a quality ranking — e.g. ordering by
  percentile sum, or omitting the "not quality" note.
- Similarity dominated by whichever category happens to have the most
  metrics. This is precisely what the `role` configuration exists to
  test against `equal`.
- A position-consistency number that is trivially 100% because the
  measurement reused the production position filter. The acceptance
  metric must be able to fail.
- Silently comparing a 200-minute player against full-season profiles.

## Constraints

- `football_ro` role for all reads; parameterized queries only.
- The metric set comes from
  `football_ai.scouting.categories.POSITION_CATEGORIES` (unioned across
  the fine groups inside each broad group), with `discipline` already
  excluded there. No new hand-written metric list.
- Vectors are built from **individual metrics**, not Day 7's category
  scores. A category mean collapses "shoots a lot, creates little" and
  "shoots little, creates a lot" onto the same point — the exact
  distinction a scout is asking about.
- Possession context is required by `CLAUDE.md`'s similarity rule
  ("takım bağlamı (topa sahip olma düzeltmesi)"). Day 7 already produces
  `possession_adjusted_value` for `defending` volume metrics; similarity
  consumes it there and the raw value for every other metric. Where the
  adjustment could not be computed, the dimension is imputed rather than
  back-filled with a raw value (see Feature vector).
- Data attribution `"openplay (Noah Bair)"` on the output model.

## Decided design

### Feature vector — one space per *broad* group

An earlier draft built one vector space per *fine* position group. A
builder check killed it: a CB vector (21 dims) and an FB vector (28 dims)
have different metrics in different slots and, under `pca`, entirely
different bases — so the cosine the acceptance metric needs between them
is undefined. Worse, z-scoring inside the fine group centres every group
on zero, erasing exactly the CB-vs-FB signal the metric is supposed to
detect. The space is therefore keyed on the **broad** group.

For a player in broad group `B` (one of GK / DEF / MID / ATT):

1. Metric set = every metric whose `category` appears in
   `POSITION_CATEGORIES[f]` for **any** fine group `f` inside `B`, in
   `metrics.yaml` order (stable, testable). Measured sizes:

   | Broad | Fine groups | Categories | Dims |
   |---|---|---|---|
   | GK | GK | goalkeeping, passing, duels | 11 |
   | DEF | CB, FB | defending, duels, passing, progression, creation | 28 |
   | MID | DM, CM, AM | defending, duels, passing, progression, creation, shooting | 35 |
   | ATT | W, FW | creation, shooting, duels, progression | 24 |

   Still sourced entirely from `POSITION_CATEGORIES` — no second list to
   drift — and `discipline` stays excluded because it is excluded there.
2. Value per metric = the possession-adjusted value when Day 7 produced
   one (`defending` + unit in {per90, count}), else the raw value.
3. **Z-score within league + broad group**: `(x - mean) / stddev` over
   qualified players in that `(comp, position_group_broad)` cell. A
   Premier League defender and a Serie A defender become comparable —
   each is "how far from his own league's defenders" — and the
   CB/FB distinction survives, because both are measured against the
   same DEF population rather than each against his own.
4. A metric that is NULL for a player (never attempted the action, so
   Day 4's `player_metrics` emits no row at all) gets z = 0, i.e.
   "league average for this broad group," and the fact is counted and
   surfaced as `imputed_dimensions` — a scout can see how much of the
   match was inferred rather than observed.

**Tradeoff, stated plainly:** z-scoring against the broad group gives
slightly coarser discrimination *among* CBs than z-scoring among CBs
would, in exchange for a measurable acceptance metric and one build path
instead of two. It also arguably reads better for scouting — "unusually
progressive for a defender" is the sentence a scout actually writes.

**Direction (`higher_is_better: false`) is deliberately NOT flipped.**
Two players who both lose the ball often genuinely share a style trait;
flipping would be a quality judgement, which this feature must not make.

**Players whose `avg_opponent_possession_pct` is NULL** (Day 7 sets
`possession_adjustment_note` for them) do not get a raw value silently
substituted into a distribution of adjusted ones — that is the mixed-
population error the project's "no silent wrongness" rule exists to
prevent. Their `defending` volume dimensions are treated as imputed
(z = 0) and counted in `imputed_dimensions`. The loaded dataset
currently has zero such players, so this is a guard, not a hot path.

### Why cosine, and why it supports the "not quality" rule

Cosine on z-scored vectors compares the *pattern* of deviations, not
their magnitude. A player who is +2 SD across the board and one who is
+1 SD across the board point in nearly the same direction — same style,
different level. That is the intended semantics. Euclidean distance would
instead make "level" dominate and quietly turn the feature into a quality
ranking.

### Weighting configurations

Weights are applied by scaling each dimension *before* cosine:

- **equal** — all weights 1.
- **role** — weight of a metric in category `c` with `k_c` metrics, out
  of `C` categories in that broad group: `1 / (C * k_c)`, so each
  category contributes equally in total.
- **pca** — PCA fitted per broad group on the z-scored matrix pooled
  across leagues; keep the smallest component count explaining ≥ 90% of
  variance; the stored vector is the projection. (`scikit-learn` — a new
  dependency, also needed Day 18 for the xG baseline.)

**Known property of `role`, accepted:** a single-metric category carries
its full category share alone. In GK, `goalkeeping` holds only
`saves_per90`, so that one metric drives a third of GK similarity. This
is `role` behaving as defined, not a bug, and it is invisible in the
acceptance metric (GK is excluded there — see Evaluation). It must
therefore be visible somewhere else: **at least one of the ten
hand-inspected queries is a goalkeeper**, so the effect is looked at by
a human before the day closes.

**PCA determinism:** component signs are arbitrary in a PCA fit and can
flip between runs, which would silently churn stored vectors. The fit
pins `random_state` and sign-normalises each component (force the
loading of largest absolute magnitude positive) so a rebuild on
unchanged data reproduces the same vectors — a test asserts this.

### Storage (new migration `005_similarity.sql`)

A table, not a view: z-scores and PCA need a fitted population, which is
a batch computation, not a per-row expression.

```
football.player_vectors(
    comp, season, player_id,
    position_group,                -- fine: the production filter
    position_group_broad,          -- the vector space this row lives in
    weighting        text,         -- 'equal' | 'role' | 'pca'
    vec              vector(35),   -- fixed width; see below
    dims             int,          -- real dimension count for this row
    metric_keys      text[],       -- the input metrics, in order
    imputed_dims     int,          -- how many were NULL -> 0
    built_at         timestamptz,
    primary key (comp, season, player_id, weighting)
)
```

**Fixed width 35 with zero padding.** pgvector's `vector(n)` requires one
declared dimension per column, and broad groups need 11–35 (MID is the
widest at 35 — every metric except `discipline` and `goalkeeping`).
Every comparison happens inside one broad group, where all rows share
the same padding, so the trailing zeros contribute identically to every
pair and change no ranking. `dims` and `metric_keys` keep the row
self-describing so nobody has to infer what dimension 12 meant.

**`metric_keys` always holds the *input* metrics**, including on `pca`
rows. For `equal` and `role`, `len(metric_keys) == dims`. For `pca`,
`dims` is the retained component count and `len(metric_keys) > dims` —
the keys record what went into the fit, which is the provenance a
scouting report has to be able to state. `SimilarityResult.metric_keys`
carries the same thing, so a `pca` result reports the features it was
derived from rather than meaningless `pc1…pcN` labels.

Populated by a script (`scripts/build_vectors.py`, `make build-vectors`)
in one transaction per full rebuild — same idempotency posture as the
Day 2 ETL. Exact search over ~1 100 qualified rows at 35 dimensions is
sub-millisecond work; an ivfflat/hnsw index is optional and left to the
builder to add only if the measured latency asks for it.

Production search pools are healthy at every fine position (smallest is
AM at 61, largest CB at 221 — see the table under Evaluation), so no
position needs a pooling fallback the way Day 4's percentiles did.

### API shape

```python
class SimilarPlayer(BaseModel):
    player_id: int
    player: str
    teams: str
    comp: str
    season: str
    position_group: str
    minutes_played: int
    matches: int
    similarity: float  # cosine, 1.0 = identical pattern
    imputed_dimensions: int


class SimilarityResult(BaseModel):
    query_player_id: int
    query_player: str
    comp: str
    season: str
    position_group: str
    weighting: str
    comparison_pool_size: int  # how many candidates were searched
    min_minutes_threshold: int
    imputed_dimensions: int  # for the query player
    metric_keys: list[str]
    results: list[SimilarPlayer]
    similarity_note: str = "Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."
    data_attribution: str = "openplay (Noah Bair)"
    generated_at: datetime
```

`PlayerNotQualifiedError` (new, alongside Day 7's `PlayerNotFoundError`)
for a sub-threshold query player, with the player's minutes and the
threshold in the message.

**The query player is excluded by `player_id`, not by row.** A player who
changed leagues mid-season has two `player_season` rows and therefore two
vectors; matching on `(comp, season, player_id)` alone would return him
as his own most-similar player at ~0.97 and nobody would notice until a
human read the list. Every row sharing the query's `player_id` is
removed, and `comparison_pool_size` counts candidates *after* that
removal. For the same reason a `player_id` can appear at most once in
`results` — the higher-similarity row wins.

**Stale vectors fail loudly.** `player_vectors` is a batch artefact, but
`config/metrics.yaml` is runtime authority (Day 4: "eşik değiştirmek
migration gerektirmez"). Adding a metric or changing a threshold
therefore invalidates stored z-scores silently. `similar_players()`
compares the stored `metric_keys` for the query player's broad group
against what `POSITION_CATEGORIES` × `metrics.yaml` produce *now* and
raises `StaleVectorsError` naming `make build-vectors` if they differ.
Cheap to check, and it converts a silent wrongness into an instruction.

### Evaluation — the acceptance metric, built so it can fail

The production function filters to the same fine position group, which
would make "position consistency" trivially 100%. So the metric is
measured **with that filter removed**:

For every qualified player, take the top-10 neighbours within their
**broad** pool (`position_group_broad`: GK/DEF/MID/ATT — already a column
on `player_season`), and compute the fraction whose **fine**
`position_group` matches the query player's. Reported **per weighting
configuration**. Target ≥ 90%.

This measures whether the vector carries real positional signal or
whether the weighting washed it out. It is an instrument, not an API.

**The qualified population (measured, 900+ minutes, all three leagues):**

| Broad | Fine groups | Pool | Base rate if ranking were random |
|---|---|---|---|
| ATT (274) | FW 172, W 102 | 274 | FW 63%, W 37% |
| DEF (422) | CB 221, FB 201 | 422 | CB 52%, FB 48% |
| MID (303) | CM 164, DM 78, AM 61 | 303 | CM 54%, DM 26%, AM 20% |
| GK (73) | GK 73 | 73 | **100% — see below** |

Two consequences the builder must honour:

1. **GK is excluded from this metric.** Its broad pool *is* its fine
   pool, so it scores 100% by construction and would inflate any
   average. Report GK's count as excluded, with the reason, rather than
   quietly folding it in.
2. **The headline number is the unweighted mean over the seven
   non-GK fine groups, not over players.** A per-player average would
   let the two big groups (CB 221, FW 172) carry the result while AM
   (61, base rate 20%) — the hardest and most informative case — barely
   moves it. The per-group table is reported in full alongside the mean.

The base-rate column is what makes the 90% target interpretable: 90% for
CB is a modest lift over a 52% coin-flip, while 90% for AM against a 20%
base rate would be a strong result.

**If no configuration reaches 90%, the day still closes** (decided with
the project owner). The deliverable is then the measured table plus a
confusion breakdown — which fine positions absorb which — and a written
explanation. Adjacent roles like AM and CM genuinely overlap on the
ball-event metrics OpenPlay carries, and that is a finding about
football and about this dataset, not a reason to iterate until a number
is hit. The lift over each group's base rate is reported next to the raw
number so the result is readable either way.

What remains unacceptable is reporting a number without saying which
configuration produced it, or presenting a shortfall as a pass. The
shortfall, if any, goes in `DECISIONS.md` next to the winning
configuration.

Reported alongside: per-configuration mean similarity of the top-10
(a configuration that calls everyone similar has not discriminated),
and query latency.

## What's left to the builder

- Module layout under `src/football_ai/scouting/` (e.g. `similarity.py`,
  `vectors.py`) and whether the z-scoring/PCA fitting lives in the build
  script or an importable function — the latter is easier to test.
- Whether `scripts/build_vectors.py` rebuilds all three weightings in one
  pass (likely, since they share the z-scored matrix) or takes a flag.
- Exact test split: pure unit tests for the weighting math and z-scoring
  against fixed numbers, `db`-marked tests for the stored vectors, the
  latency assertion, and the sub-threshold error.
- Whether PCA component counts are stored per broad group in a table or
  recomputed — recomputing is fine given the determinism rules above.
- Whether `player_vectors` gets a pgvector index at all; at ~1 100 rows
  exact search is expected to clear the 200 ms budget comfortably, so
  add one only if the measurement says otherwise.
- The format of the 10 hand-inspected queries' write-up (a report file
  under `reports/` follows the project's existing habit).
