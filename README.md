# Football Intelligence AI

AI-assisted football scouting and player performance analysis for the **2025/26**
season of the Premier League (`eng`), La Liga (`esp`) and Serie A (`ita`).

The platform answers scouting questions over event-level data: per-90 and
percentile player metrics, similarity search, natural-language SQL, a
methodology knowledge base, and an agent that composes these into scouting
reports. A core rule runs through the whole project: **the LLM never produces
numbers.** Every figure in a report comes from a tool or database query; the
model only writes the interpretation.

Status: **Day 1 complete — data validated.**
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

```bash
uv sync                     # create .venv (Python 3.12) and install locked deps
uv run pre-commit install   # enable commit-time lint/format hooks
uv run pytest               # 28 unit tests
```

On Windows, if `uv` is not on your `PATH` after `pip install --user uv`, add
`%APPDATA%\Python\Python311\Scripts` to it. If `uv` fails with
`Missing expected target directory for Python minor version link`, install the
interpreter elsewhere once: `UV_PYTHON_INSTALL_DIR=C:\Users\<you>\.uv-python uv python install 3.12`.

## Commands

| Command | Purpose |
| --- | --- |
| `uv run pytest` | unit tests (real-data tests excluded) |
| `uv run pytest -m data` | tests against the real OpenPlay dataset |
| `uv run python scripts/validate_openplay.py reports` | data validation report |
| `uv run python scripts/explore_day1.py` | append structural findings to the report |
| `uv run ruff check . && uv run ruff format .` | lint and format |

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
