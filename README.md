# Football Intelligence AI

AI-assisted football scouting and player performance analysis for the **2025/26**
season of the Premier League (`eng`), La Liga (`esp`) and Serie A (`ita`).

The platform answers scouting questions over event-level data: per-90 and
percentile player metrics, similarity search, natural-language SQL, a
methodology knowledge base, and an agent that composes these into scouting
reports. A core rule runs through the whole project: **the LLM never produces
numbers.** Every figure in a report comes from a tool or database query; the
model only writes the interpretation.

Status: **Day 4 complete — metric definitions and percentiles live.**
Plan: [docs/PLAN.md](docs/PLAN.md) · Decisions: [DECISIONS.md](DECISIONS.md)

## Data

Source: **openplay (Noah Bair)**, release `data-v0.1.0`, licensed
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Raw parquet/csv files are never committed. The `openplay` package downloads
them on first use, verifies SHA-256 against `checksums.json` and caches them
locally (`%LOCALAPPDATA%\openplay\cache\data-v0.1.0` on Windows).

Facts worth knowing before writing queries:

- The season is written `"2025/26"` and stored as `"2526"`.
- Coordinates are 0–100 and **every team attacks towards x=100**. For metres:
  `x × 1.05`, `y × 0.68`.
- `minutes_played` is *expanded* minutes (stoppage included), so a full match is
  ~98–101 minutes, not 90. Per-90 values are therefore 8.2–10.8% lower than
  sources that assume a nominal 90 — only compare within OpenPlay. See D-004.
- `player_match_stats.position` is the **starting** position; players who came
  on read `Sub`. See D-005.
- `player_season_stats` aggregates per player **and** team, so a mid-season
  transfer produces two rows.
- There is no pressure event and no progressive-carry data.

## Setup

Needs Docker and `uv`. Python 3.12 is installed by `uv` itself.

```bash
cp .env.example .env        # then set the two passwords
uv sync                     # create .venv and install locked deps
uv run pre-commit install   # enable commit-time lint/format hooks
make setup                  # db-up + migrate + validate + etl, from scratch
make test                   # 47 unit tests
```

`make setup` takes about **65 seconds** on an empty volume and is safe to
re-run: it is idempotent end to end.

Windows notes (all were hit while building this):

- Install `uv` with the official installer, not `pip`:
  `irm https://astral.sh/uv/install.ps1 | iex`. It targets `~\.local\bin`,
  which is already on `PATH` in most setups, so no shell restart is needed.
  A `pip install --user uv` lands in `%APPDATA%\Python\Python3xx\Scripts`,
  which usually is *not* on `PATH`.
- If `uv` is on disk but not on `PATH`, you can pass it per command instead:
  `make UV="$APPDATA/Python/Python311/Scripts/uv.exe" setup`.
- If `uv` fails with `Missing expected target directory for Python minor
  version link`, install the interpreter elsewhere once:
  `UV_PYTHON_INSTALL_DIR=C:\Users\<you>\.uv-python uv python install 3.12`.
- `make` is not installed by default: `winget install ezwinports.make`.
- PATH edits: use `[Environment]::SetEnvironmentVariable(...,"User")`, not
  `setx`. `setx` silently truncates at 1024 characters, and a typical user
  PATH here is already over 1000.

## Commands

Run `make help` for the current list.

| Command | Purpose |
| --- | --- |
| `make setup` | `db-up` + `migrate` + `validate` + `etl` from nothing |
| `make db-up` / `db-down` / `db-reset` | start / stop / destroy Postgres |
| `make db-shell` | psql session as the owner role |
| `make migrate` | apply pending SQL migrations |
| `make etl` | full reload of OpenPlay 2025/26 into Postgres |
| `make etl-bench` | measure `COPY` against `pandas.to_sql` |
| `make counts` | row counts per table |
| `make validate` | regenerate the data validation report and findings |
| `make ask Q="..."` | natural-language question (needs an LLM key) |
| `make schema-prompt` | print the schema description the model is given |
| `make llm-models` | list the models your API key can actually reach |
| `make eval-sql` | 40-question text-to-SQL benchmark (LLM key + loaded db) |
| `make eval-sql-both` | same, strong + weak model, with a disagreement table |
| `make eval-sql-gold` | validate the gold set: guard + `EXPLAIN`, no LLM (what CI runs) |
| `make test` | unit tests (no database, no dataset) |
| `make test-data` | tests against the real OpenPlay dataset |
| `make test-db` | tests against the loaded database |
| `make lint` / `make fmt` / `make check` | ruff check / format / all of it |

## Database

PostgreSQL 17 with pgvector, one container, schema `football`.

```
teams  players ──┐
                 ├── matches ──┬── lineups              (full matchday squad)
                 │             ├── player_match_stats   (players who appeared)
                 │             ├── shots
                 │             └── passes               (events where type='Pass')
                 └── data_quality, data_quality_features

views:  position_map          one position group per player per league-season
        player_season_club    season totals per player AND club   (1 771 rows)
        player_season         clubs combined, position attached   (1 723 rows)
        player_per90          per-90 rates and ratio metrics
```

Design choices that are not obvious, with the reasoning in `DECISIONS.md`:

- **`comp` and `season` are repeated on every fact table** (D-008). The most
  common filter in a scouting query is league + season; paying two small
  columns to avoid a join is a direct text-to-SQL accuracy win. Player and
  team *names* are denormalised for the same reason — safe only because the
  season is finished and the ETL is a full reload, so copies cannot drift.
- **Qualifier columns are renamed**: `q_Cross` → `is_cross`,
  `q_Longball` → `is_long_ball`. A model has no idea what `q_Longball` is.
  `is_completed` is derived from `outcome` so no string literal needs
  remembering.
- **Natural keys, no surrogates** — all verified unique against the source
  before being written into the schema. The raw event stream is *not* unique
  on `(match_id, event_id, event_id_sub)`: the source reuses an id between an
  `OffsideGiven` event and an unrelated event, 82 times across the three
  leagues. The `Pass` subset is clean, which is why `passes` can use that key.
- **Two roles from day one** (D-013): `football_etl` writes, `football_ro`
  only selects and carries a server-side `statement_timeout`. From day 5 the
  SQL agent only ever sees the second one.
- **Idempotency differs by data type** (D-010): the frozen fact tables are
  `TRUNCATE` + `COPY` in one transaction (TRUNCATE is transactional in
  Postgres, so a failed load rolls back to the previous contents).
  `data_quality` is append-only history, keyed by the report's own
  `generated_at` rather than by the loader's clock.

## Day 2 — load

| Table | Rows | Matches source |
| --- | --- | --- |
| `teams` | 60 | 3 leagues x 20 |
| `players` | 2 166 | filtered from 20 782 in the source |
| `matches` | 1 140 | 3 x 380 |
| `lineups` | 49 901 | 15 189 + 16 939 + 17 773 |
| `player_match_stats` | 35 373 | 11 492 + 11 953 + 11 928 |
| `shots` | 28 434 | 9 543 + 9 510 + 9 381 |
| `passes` | 1 083 374 | 362 739 + 362 956 + 357 679 |

Measured on this machine (`make etl-bench`, 50 000 pass rows):
`COPY` 1.01s vs `pandas.to_sql` 2.51s — **2.5x**, not the order of magnitude
this choice is usually sold with. The reason is that ~71% of COPY time is
Python converting pandas scalars, not the server; see D-011 for the numbers
and the optimisation we deliberately did not take.

Tests: **47** unit (no database), **4** against the real dataset, **47**
against the loaded database — including 12 that assert the read-only role
cannot write, cannot create objects, and really does get its queries
cancelled by the server-side timeout.

## Day 3 — positions and per-90

Every player gets one position group per league-season, voted from
minute-weighted **starting** positions (substitute minutes carry no positional
information — the source writes `Sub`). Eight groups, with a four-group
fallback pool for league-groups too small to support a percentile:

| Group | Raw codes | eng | esp | ita |
| --- | --- | --- | --- | --- |
| GK | GK | 25 | 24 | 24 |
| CB | DC | 71 | 72 | 80 |
| FB | DL, DR, **DML, DMR** | 61 | 69 | 64 |
| DM | DMC | 42 | 27 | 10 |
| CM | MC | 34 | 49 | 83 |
| AM | AMC | 36 | 16 | 14 |
| W | AML, AMR, ML, MR | 39 | 48 | 9 |
| FW | FW, FWL, FWR | 49 | 56 | 70 |

Counts are players with 900+ minutes. `DML`/`DMR` map to full-back, not
defensive midfield: they are the wing-back slot in a 3-5-2, and Serie A plays
them for 9.1% of minutes against 6.2% for `DL`/`DR` (England is the reverse).
Treating them as midfielders left Serie A with 22 full-backs; as wing-backs the
three leagues read 61/69/64. See D-014.

`position_map` also carries `position_source` and `position_share`, because the
answer is not equally trustworthy for everyone:

- `starts` (1 519 players) — voted from real starting minutes
- `main_position` (74) — never started; fell back to the players dimension
- `unknown` (130) — never started and no fallback either

A third source was measured and rejected: classifying by median pass position
scored 70.9% overall but **32% for AM and 37% for CM**, and the players who
need it average 13 passes. Saying "unknown" beats guessing. None of the 130
reaches 900 minutes, so no percentile population is affected — asserted by a
test. `position_share` is below 0.6 for roughly one player in six, which is
genuine positional ambiguity a report should surface rather than hide.

### Per-90 verification

`player_per90` follows D-004: per-90 divides by real expanded minutes, and
ratios are ratios of sums with `NULL` (not 0) on a zero denominator.

Checked against `op.player_season_stats(per90=True)` for **all 1 064**
player-club rows with 900+ minutes, on `npxg`, `xa` and `progressive_passes`:

```
largest absolute difference: 0.000e+00   (tolerance 0.01)
```

Exactly zero, where day 1 measured `2.86e-08`. The difference is where the
widening happens: the source columns are `float32`, and day 1 summed 20-38
match values before widening. The views cast to `double precision` *before*
summing, which reproduces openplay bit for bit. Reproducing the old number by
deliberately summing in `float32` confirmed it (D-017).

## Day 4 — metrics and percentiles

[config/metrics.yaml](config/metrics.yaml) is the source of truth for **38
metrics** across 8 categories. Each one declares its definition, formula, unit,
direction and the column it reads. The ETL validates and loads it into
`football.metric_definitions` and `football.metric_config`; the
`football.player_metrics` view computes values and percentiles live, so
changing a threshold in the yaml changes behaviour without a migration (D-020).

```sql
select player, value, percentile, comparison_group_size
from football.player_metrics
where metric = 'npxg_xa_per90' and comp = 'eng' and position_group = 'W'
order by percentile desc;
```

**Percentile method.** Tie-aware midrank, `(players below + half the players
tied) / n`, oriented so **100 always means "best in the group"** — including
for `miscontrols_per90` and the other lower-is-better metrics, where the
percentile is inverted so a radar never has to special-case a direction.

Measured on the smallest real group (n=10):

| | lowest player | highest player |
| --- | --- | --- |
| `percent_rank()` | **0.0** | 100.0 |
| `cume_dist()` | 10.0 | **100.0** |
| midrank (chosen) | 5.0 | 95.0 |

Neither extreme gets an absolute 0 or 100, because in a finite sample neither
claim is true. Across all 40 409 rows the range is 0.49 – 99.51, and no two
players with equal values receive different percentiles.

**Comparison groups.** League + fine position group where possible; where a
cell is below 20 players, the role is kept and the leagues are pooled; below 20
even then, no percentile is reported at all and `comparison_scope` reads
`insufficient`.

| Scope | Rows | Group size |
| --- | --- | --- |
| `league_position` | 38 430 | 23 – 82 |
| `position_pooled` | 1 963 | 25 – 102 |
| `insufficient` | 16 | 8 |

Pooling leagues rather than widening the role is a deliberate deviation from
the "same league" rule, made on measured homogeneity (coefficient of variation,
lower is better):

| Metric | same league + role | pooled leagues + role | same league + broad |
| --- | --- | --- | --- |
| `npxg_per90` | 0.932 | **1.264** | 1.399 |
| `crosses_per90` | 0.918 | **0.938** | 1.012 |
| `tackles_per90` | 0.525 | **0.518** | 0.687 |

Comparing a Serie A winger to European wingers beats comparing them to Serie A
forwards. See D-019.

The 16 unranked rows are the 8 goalkeepers who attempted a non-penalty shot:
`npxg_per_shot` cannot be ranked against a pool of 8.

Ten values were recomputed by hand from `player_match_stats` and all ten
matched; every one is now a test in `tests/test_metrics_db.py`.

## Day 6 — text-to-SQL accuracy

Gold set: [evals/sql/questions.yaml](evals/sql/questions.yaml) — 40 questions in
8 categories, each with a reference query written and verified by hand against
the loaded database. Latest report:
[reports/eval_sql_latest.md](reports/eval_sql_latest.md).

The judge is the **result set**, not the SQL text: a query written nothing like
the reference that returns the same rows is a correct answer. Four dimensions
are scored separately, because a single accuracy number hides four failures
that need four different fixes — did it run, are the rows right, is the output
usable (a percentile with no comparison group size is not), and was the number
reached the right way (a 900-minute filter on a question about season totals can
return identical rows and still be wrong reasoning).

### Where it stands

| | |
| --- | --- |
| Run | `gemini/gemini-3.1-flash-lite`, 2026-11-16, 279 s, 0 infrastructure errors |
| Accuracy | **52.8%** (19 of 36) — **below the 70% target** |
| Denominator | 36 of 40; the 4 `unanswerable` questions have no reference result set |
| Strong model | **not measured** — see below |

**The target is not met and not yet properly measured.** The threshold applies
to the strong model, and every candidate was unavailable on the day this ran:
`gemini-3.8-flash` and `3.7-flash` returned 503 (saturation), `3.6-flash` and
`3.5-flash` exhausted the free-tier daily quota after ~15 questions. The number
above is the **weak** model, which the design treats as a diagnostic rather
than a gate (D-028). A strong-model run is the first thing Day 7 owes.

### Accuracy by category

| Category | n | correct | ran | required columns | no forbidden structure |
| --- | --- | --- | --- | --- | --- |
| `teams` | 5 | 100% | 5/5 | 5/5 | 5/5 |
| `filters` | 5 | 100% | 5/5 | 5/5 | 5/5 |
| `percentiles` | 5 | 80% | 5/5 | 5/5 | 5/5 |
| `totals` | 5 | 40% | 5/5 | 5/5 | 5/5 |
| `transfers` | 5 | 40% | 5/5 | 3/5 | 5/5 |
| `rates` | 6 | 17% | 6/6 | 2/6 | 6/6 |
| `match_detail` | 5 | 0% | 3/5 | 5/5 | 5/5 |
| `unanswerable` | 4 | n/a | 4/4 | 4/4 | 4/4 |

This table is the point of the whole exercise. The two categories the developer
guessed would be hardest — ratios and transferred players — are indeed 17% and
40%. But `match_detail` at 0% was not predicted by anyone, and it is the
category the schema prompt says least about.

One number is better than expected: **no question in any category violated a
forbidden structure.** The over-broad minutes rule that D-025 found and fixed
has stayed fixed, including in the model that originally exposed it.

### The three most common failures

**1. Dropping the context columns the prompt asks for — 6 of 17 wrong answers**
(`totals-02`, `totals-05`, `transfers-01`, `transfers-02`, `transfers-04`,
`match_detail-01`). The prompt says to return the sample a ranking rests on
(`minutes_played`, `matches`) and the club alongside the player. The model
returns three columns where the reference has five:

```sql
-- asked: La Liga'da en çok sarı kart gören 7 oyuncu
SELECT player, teams, yellow_cards FROM football.player_season
WHERE comp = 'esp' ORDER BY yellow_cards DESC LIMIT 7
```

The seven names and seven numbers are right. Measured rather than assumed: when
those six are re-scored against only the columns the model chose to return,
**three become correct** (`totals-02`, `totals-05`, `transfers-02`) and three
are wrong anyway. So this failure class costs 3 questions — 52.8% would be
61.1% — and the remaining gap is real.

That the comparison conflates "the right answer" with "the right output shape"
is a known property of the prefix rule, not an accident: the reference's
columns must appear as a prefix, extra trailing columns are free. It is worth
revisiting whether the context columns belong in `required_columns` alone.

**2. Dropping the sample column on rate questions — 4 of 17**
(`rates-02`, `rates-03`, `rates-04`, `rates-06`). Same root cause as (1) but
concentrated: `required_columns` is 2/6 in `rates`, so four of the six rate
questions came back without `minutes_played`. A per-90 value without the
minutes behind it is the exact number a scouting report is not allowed to
print.

**3. Not knowing which relation holds a column — 2 of 17**
(`match_detail-03`, `match_detail-04`). Both failed at the database, not at the
guard:

```
column "player" does not exist
LINE 1: SELECT player, team_id, xg, mat...
```

`football.shots` carries `player_id`, not `player`; the name lives in
`football.players` and needs a join. The schema prompt lists both relations and
the declared foreign keys between them, so the information was present and the
model did not use it. These two are the clearest prompt-improvement target in
the whole run.

### The repair loop does not help

`generate.py` retries once with the guard's refusal reason attached, and its own
docstring said Day 6 would measure whether that is worth the latency. It is not:

| | |
| --- | --- |
| Passed on the first attempt | 38 |
| Fixed by the repair attempt | **0** |
| Still refused after the repair | 2 |

Zero out of 40. In this run the repair attempt never converted a refusal into a
working query, which is evidence for the comment's original guess — a model that
could not use the refusal reason the first time repeats itself. Worth
re-measuring on the strong model before removing it.

### What CI checks

`make eval-sql-gold` runs on every push and calls no LLM. It validates the gold
set against the live schema with `EXPLAIN` on a migrated-but-empty database, so
a renamed column fails a pull request without an OpenPlay download and without
a provider outage ever turning the build red.

Six checks, and they earned their place immediately: on their first run they
found **five defects in the gold set this developer had just written** — a
reference that used the view it forbade, two that cut on a tie (where two
different answers are both correct and the comparator cannot tell), and two
that ranked by a `DESC` column containing NULLs, which Postgres sorts *first*.

## Day 1 — data validation

Full report: [reports/data_validation_2526.md](reports/data_validation_2526.md)
(machine-readable: `reports/data_validation_2526.json`).

Thresholds are **targets, not gates**. Each check returns `pass`, `degraded` or
`disabled`; a failure never stops the run, it is reported and the affected
feature is flagged. Below a critical floor the feature is switched off entirely
and the agent will not call that tool (D-003).

| Check | Target | Premier League | La Liga | Serie A |
| --- | --- | --- | --- | --- |
| `match_coverage_pct` | ≥ 99 | 100.0 `pass` | 100.0 `pass` | 100.0 `pass` |
| `shot_xg_filled_pct` | ≥ 99 | 100.0 `pass` | 100.0 `pass` | 100.0 `pass` |
| `pass_end_xy_filled_pct` | ≥ 99 | 100.0 `pass` | 100.0 `pass` | 100.0 `pass` |
| `coords_out_of_range` | ≤ 0 | 0 `pass` | 0 `pass` | 0 `pass` |
| `score_mismatch_pct` | ≤ 1 | 0.0 `pass` | 0.0 `pass` | 0.0 `pass` |
| `unknown_minutes_pct` | ≤ 1 | 0.0 `pass` | 0.0 `pass` | 0.0 `pass` |

All 10 derived features are `pass`; `known_gaps` and `data_issues` are empty for
all three leagues.

| Volume | Premier League | La Liga | Serie A |
| --- | --- | --- | --- |
| matches | 380 | 380 | 380 |
| events | 577 884 | 577 205 | 562 672 |
| shots | 9 543 | 9 510 | 9 381 |
| players | 537 | 600 | 586 |
| season goals | 1 045 | 1 024 | 922 |
| season xG | 1 099.2 | 1 023.4 | 982.4 |

Cross-checks run on day 1:

- **Per-90 formula verified.** Our `Σ count / Σ minutes_played × 90` matches
  `op.player_season_stats(per90=True)` for every player with 900+ minutes in all
  three leagues on `npxg`, `xa` and `progressive_passes`. Largest absolute
  difference: **2.86e-08** (tolerance ±0.01).
- **Ratios must be ratios of sums.** Averaging per-match pass percentages instead
  understates pass accuracy by 6.9–9.7 percentage points.
- **One check is vacuous.** `unknown_minutes_pct` can never fail, because
  `player_match_stats` only contains players who actually appeared (25 080 starters
  + 10 293 `Sub` rows = 35 373 = total rows). Day 2 replaces it with a
  `team_minutes_ratio` check, which does carry signal (it drops below 1 in matches
  with a red card). See D-003.

## Attribution

Data: **openplay (Noah Bair)** — CC-BY 4.0.
