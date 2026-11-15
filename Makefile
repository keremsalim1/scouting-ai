# Football Intelligence AI - task entry points.
#
# Portability notes, learned the hard way on Windows:
#  * GNU make drives cmd.exe here, not sh, so every recipe below is a single
#    plain command. Shell loops live in scripts/*.py instead (see db_wait).
#  * `uv` may not be on PATH. Override it per-invocation if so:
#      make UV="$APPDATA/Python/Python311/Scripts/uv.exe" etl
#    or put its directory on PATH once (see README).
#  * `-f infra/...` moves compose's project directory to infra/, so
#    --env-file has to point back at the repo-root .env.

UV ?= uv
COMPOSE ?= docker compose -f infra/docker-compose.yml --env-file .env
PSQL_USER ?= football_etl
PSQL_DB ?= football

.PHONY: help db-up db-down db-reset db-shell db-wait migrate etl etl-bench counts \
        ask schema-prompt llm-models validate test test-data test-db lint fmt check setup

help:
	@echo "setup      db-up + migrate + validate + etl  (first run, from scratch)"
	@echo "db-up      start Postgres (pgvector) and wait until it accepts queries"
	@echo "db-down    stop Postgres, keep the data volume"
	@echo "db-reset   stop Postgres and DELETE the data volume"
	@echo "db-shell   psql session as the owner role"
	@echo "migrate    apply pending SQL migrations"
	@echo "etl        load OpenPlay 2025/26 into Postgres (full reload)"
	@echo "etl-bench  measure COPY against pandas.to_sql"
	@echo "counts     print row counts per table"
	@echo "ask        natural-language question: make ask Q=\"...\" (needs an LLM key)"
	@echo "schema-prompt   print the schema description the model is given"
	@echo "llm-models list the models your API key can actually reach"
	@echo "validate   regenerate the data validation report and findings"
	@echo "test       unit tests        test-data  real OpenPlay    test-db  database"
	@echo "lint fmt   ruff check / ruff format"
	@echo "check      lint + format check + unit tests"

setup: db-up migrate validate etl

db-up:
	$(COMPOSE) up -d
	$(UV) run python scripts/db_wait.py

db-wait:
	$(UV) run python scripts/db_wait.py

db-down:
	$(COMPOSE) down

db-reset:
	$(COMPOSE) down -v

db-shell:
	$(COMPOSE) exec db psql -U $(PSQL_USER) -d $(PSQL_DB)

migrate:
	$(UV) run python scripts/migrate.py

etl:
	$(UV) run python scripts/etl.py

etl-bench:
	$(UV) run python scripts/etl.py --benchmark

counts:
	$(UV) run python scripts/etl.py --counts

ask:
	$(UV) run python scripts/ask.py $(Q)

schema-prompt:
	$(UV) run python scripts/ask.py --show-schema

llm-models:
	$(UV) run python scripts/llm_models.py

validate:
	$(UV) run python scripts/validate_openplay.py reports
	$(UV) run python scripts/explore_day1.py

test:
	$(UV) run pytest

test-data:
	$(UV) run pytest -m data

test-db:
	$(UV) run pytest -m db

lint:
	$(UV) run ruff check .

fmt:
	$(UV) run ruff format .

check: lint
	$(UV) run ruff format --check .
	$(UV) run pytest
