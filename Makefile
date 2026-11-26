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
        ask schema-prompt llm-models validate test test-data test-db lint fmt check setup \
        build-vectors eval-similarity ingest-kb kb-search \
        eval-sql eval-sql-both eval-sql-gold eval-sql-merge \
        eval-sql-batch1 eval-sql-batch2 eval-sql-batch3 eval-sql-smoke

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
	@echo "build-vectors   build similarity vectors into pgvector (needs a loaded db)"
	@echo "eval-similarity position consistency for all three weightings (needs vectors)"
	@echo "eval-sql        40-question text-to-SQL benchmark (needs an LLM key + loaded db)"
	@echo "eval-sql-both   same, strong + weak model, with a disagreement table"
	@echo "eval-sql-gold   validate the gold set: guard + EXPLAIN, no LLM (what CI runs)"
	@echo "eval-sql-batch1/2/3  one day's worth of questions (free tier is 20 req/day)"
	@echo "eval-sql-merge  stitch the batches into one accuracy number (no LLM call)"
	@echo "eval-sql-smoke  one question per category: quick regression, 8 requests"
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

# The benchmark itself is local: it needs an API key and a loaded database, and
# a provider 503 must never turn a pull request red. CI runs eval-sql-gold.
#
# The models are variables because the newest flash model is the most contended
# one: gemini-3.8-flash returned 503 on 2 of 5 questions when this was wired
# up, which is an unusable measurement. Override per run rather than editing a
# recipe:  make eval-sql-both MODEL_STRONG=gemini/gemini-3.5-flash
MODEL_STRONG ?= gemini/gemini-3.8-flash
MODEL_WEAK ?= gemini/gemini-3.1-flash-lite

# Retrieval mode for `make kb-search`: dense | hybrid | hybrid_rerank.
# Day 11 ablates all three, so all three are reachable by hand.
MODE ?= hybrid_rerank

build-vectors:
	$(UV) run python scripts/build_vectors.py

ingest-kb:
	$(UV) run python scripts/ingest_kb.py

# Q is quoted: unquoted, an apostrophe ("Mbappé'nin maaşı") is a shell syntax
# error and a `*` expands to a directory listing that silently becomes part of
# the query. The second one is worse than the crash.
kb-search:
	$(UV) run python scripts/kb_search.py --mode $(MODE) -- "$(Q)"

eval-similarity:
	$(UV) run python scripts/eval_similarity.py

eval-sql:
	$(UV) run python scripts/eval_sql.py --model $(MODEL_STRONG)

eval-sql-both:
	$(UV) run python scripts/eval_sql.py --models $(MODEL_STRONG),$(MODEL_WEAK)

# Free-tier reality: the strong flash models allow 20 requests per DAY, while
# the gold set has 40 questions. So the suite is run in batches and stitched
# back together. Batch 1 is 16 questions, batch 2 is 15, batch 3 is 9 - each
# inside the daily allowance even if a few questions need a repair attempt.
# RPD resets at midnight Pacific.
eval-sql-batch1:
	$(UV) run python scripts/eval_sql.py --model $(MODEL_STRONG) --only totals-01,totals-02,totals-03,totals-04,totals-05,rates-01,rates-02,rates-03,rates-04,rates-05,rates-06,percentiles-01,percentiles-02,percentiles-03,percentiles-04,percentiles-05

eval-sql-batch2:
	$(UV) run python scripts/eval_sql.py --model $(MODEL_STRONG) --only transfers-01,transfers-02,transfers-03,transfers-04,transfers-05,teams-01,teams-02,teams-03,teams-04,teams-05,match_detail-01,match_detail-02,match_detail-03,match_detail-04,match_detail-05

eval-sql-batch3:
	$(UV) run python scripts/eval_sql.py --model $(MODEL_STRONG) --only filters-01,filters-02,filters-03,filters-04,filters-05,unanswerable-01,unanswerable-02,unanswerable-03,unanswerable-04

# One question per category. 8 requests, so it fits the daily free-tier
# allowance and can be run after every prompt change.
eval-sql-smoke:
	$(UV) run python scripts/eval_sql.py --model $(MODEL_STRONG) --smoke

# Stitch the batches into one accuracy number. Makes no provider call.
eval-sql-merge:
	$(UV) run python scripts/eval_sql.py --merge reports/eval_sql --model $(MODEL_STRONG)

eval-sql-gold:
	$(UV) run python scripts/eval_sql_gold.py

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
