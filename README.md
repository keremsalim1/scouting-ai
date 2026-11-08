# Football Intelligence AI

AI-assisted football scouting and player performance analysis for the **2025/26**
season of the Premier League (`eng`), La Liga (`esp`) and Serie A (`ita`).

The platform answers scouting questions over event-level data: per-90 and
percentile player metrics, similarity search, natural-language SQL, a
methodology knowledge base, and an agent that composes these into scouting
reports. A core rule runs through the whole project: **the LLM never produces
numbers.** Every figure in a report comes from a tool or database query; the
model only writes the interpretation.

Status: **Day 2 complete — data validated and loaded into Postgres.**
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

Windows notes (all three were hit while building this):

- If `uv` is not on `PATH` after `pip install --user uv`, either add
  `%APPDATA%\Python\Python311\Scripts` to it, or pass it per command:
  `make UV="$APPDATA/Python/Python311/Scripts/uv.exe" setup`.
- If `uv` fails with `Missing expected target directory for Python minor
  version link`, install the interpreter elsewhere once:
  `UV_PYTHON_INSTALL_DIR=C:\Users\<you>\.uv-python uv python install 3.12`.
- `make` is not installed by default: `winget install ezwinports.make`.

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
