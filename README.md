# Football Intelligence AI

AI-assisted football scouting and player performance analysis for the **2025/26**
season of the Premier League (`eng`), La Liga (`esp`) and Serie A (`ita`).

Status: **Day 1 — data validation.** See [docs/PLAN.md](docs/PLAN.md) for the
24-day plan and [DECISIONS.md](DECISIONS.md) for technical decisions.

## Setup

```bash
uv sync                 # create .venv and install locked dependencies
uv run pre-commit install
uv run pytest           # unit tests (real-data tests: uv run pytest -m data)
```

Requires Python 3.12 (uv installs it automatically).

## Data

Source: **openplay (Noah Bair)**, release `data-v0.1.0`, licensed
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Raw parquet/csv files are never committed; they are downloaded into `data/`
on first use and ignored by git.

## Commands

| Command | Purpose |
| --- | --- |
| `uv run pytest` | unit tests (data tests excluded) |
| `uv run pytest -m data` | tests against the real OpenPlay dataset |
| `uv run python scripts/validate_openplay.py reports` | data validation report |
