# Day 9 — RAG knowledge base: corpus, chunking, metadata: design

## Intent and why

Day 9 (`docs/PLAN.md` row 32) builds the content layer that Day 10's
`methodology_search` tool and Week 3's scouting-report agent will read
from. The project's hard rule is "LLM sayı üretmez" — the LLM never
invents a number, only interprets ones the database already produced.
RAG is the mechanism for the adjacent problem: the LLM also should not
invent *scouting methodology* ("is a high pass-completion rate good for
a CB," "why do we possession-adjust only defending metrics"). That
knowledge has to live in retrievable text the agent can cite, written by
the project, not recalled from the model's training data.

Day 9 produces the corpus and the ingestion pipeline. Retrieval (hybrid
dense + full-text, RRF, reranking) is Day 10 and out of scope here.

## Goals

- `kb/` directory: ≥ 25 markdown documents, each with YAML frontmatter
  (`title`, `topic`, `source`), covering three groups agreed with the
  user:
  - **A — metric category notes** (8): one per `metrics.yaml` category
    (shooting, creation, passing, progression, defending, duels,
    discipline, goalkeeping) — how to read that category, common
    misreadings.
  - **B — project methodology notes** (9): per-90 normalization, the
    900-minute threshold, percentile methodology (midrank, pooling
    fallback), possession adjustment, position groups, what similarity
    does and does not mean, z-score + cosine intuition, xG and
    regression to the mean, sample-size warnings.
  - **C — data dictionary / source notes** (5+): OpenPlay data model and
    license, season vs season_club, the possession proxy and its limits,
    the data-quality pass/degraded/disabled policy, and a metric glossary
    document (all 38 metrics, one line each — this one document is
    expected to produce many chunks on its own).
  - Content is summarized by the project author from known public
    sources (StatsBomb/FBref-style glossaries, general scouting
    writing), in the author's own words — not copied, not LLM-invented
    numbers or claims about this project's own data (those are sourced
    from `metrics.yaml` / `CLAUDE.md` directly).
- A chunker that splits on markdown `##` headings, then further splits
  any section over ~500 words at a paragraph boundary. No fixed-size
  sliding window.
- `kb_chunks` table in pgvector (new migration `008_kb.sql`, mirroring
  `player_vectors`' table-not-view posture from Day 8): `doc_id`,
  `chunk_index`, `topic`, `source`, `title`, `content`, `content_hash`,
  `embedding vector(1024)` (bge-m3 dense output dimension).
- `make ingest-kb`: reads `kb/*.md`, chunks, embeds (bge-m3 dense vector
  only — sparse/multi-vector output is discarded this day, Day 10's
  job), writes in one transaction (`TRUNCATE` + insert — same
  idempotency posture as the Day 2 ETL and Day 8's vector build).
- Embedding model: `bge-m3` via `sentence-transformers`, run locally.
  No API cost (student budget constraint). Chosen over
  `multilingual-e5-large` because Day 10 needs sparse + dense from the
  same family for hybrid search/RRF, and bge-m3 produces both without a
  second model.
- Duplicate detection: `content_hash` (sha256 of normalized chunk text)
  unique per `(doc_id, content_hash)`; `make ingest-kb` reports and skips
  exact duplicate chunks rather than silently re-inserting them.

## Non-goals

- Retrieval, hybrid search, RRF, reranking (`bge-reranker-v2-m3`) — Day 10.
- Answering real user questions through the KB — Day 10/13.
- Sparse or multi-vector embedding storage — bge-m3 produces them, Day 9
  only persists the dense vector.
- Evaluation of retrieval quality (recall@5, faithfulness) — Day 11.
- Automatic sourcing/scraping of external content — notes are written by
  hand, not fetched.

## Anti-goals (failure even if it runs)

- A corpus with fewer than 25 *chunks* that technically has 25 *files*
  but one-sentence content — the acceptance criterion is chunk-level
  (source + topic per chunk), not file-count theater.
- Silent duplicate chunks on a second `make ingest-kb` run (breaks the
  "kopya yok" acceptance criterion and would double-count in retrieval
  rankings later).
- A chunk with no `source` or `topic` — every retrieval result must be
  attributable, matching the project's citation requirement for Day 10.

## Decided (user + this conversation)

- File format: one markdown file per note, YAML frontmatter.
- Chunking: heading-based, paragraph-boundary split for oversized
  sections.
- Embedding model: bge-m3, local, dense vector only this day.
- Metadata schema: `doc_id`, `chunk_index`, `topic`, `source`, `title`,
  `content`, `content_hash`, `embedding`.
- Three content groups (A/B/C above) and their topic list, agreed with
  the user.

## Left to the builder (settled by builder check, recorded here as calls made)

- `doc_id` = the markdown filename stem (e.g. `shooting-category.md` →
  `shooting-category`), not a frontmatter field. Renaming a file changes
  its chunks' identity under the idempotent `TRUNCATE`+insert, which is
  the same behavior Day 8 accepts for its natural keys — no new rule
  needed.
- 25-chunk threshold is **measured, not pre-guaranteed** by a heading-count
  rule. Write the notes, run `make ingest-kb`, check the chunk count; if
  short, split a section further or add a note. Same posture as Day 8's
  position-consistency number: measured after the fact, not designed
  backward from a target.
- `content_hash` normalization: strip leading/trailing whitespace and
  collapse runs of internal whitespace to one space; case and punctuation
  are left untouched (two chunks that differ only in a rephrased sentence
  must hash differently — this is accidental-duplicate detection, not
  fuzzy matching).
- `topic` is a migration-level `check constraint` (mirrors Day 8's
  `weighting` check constraint in `player_vectors`) listing the fixed
  A/B/C topic values. Adding a new note with an existing topic needs no
  migration; adding a new *topic* does.
- `kb/` stays flat (no A/B/C subdirectories); `topic` in frontmatter is
  the single source of grouping, so there is one place to look up a
  note's category instead of two.
- Exact bge-m3 dense dimension (1024 is bge-m3's standard dense output;
  confirm against the installed model version before migration).
- Exact Python dependency (`FlagEmbedding` vs `sentence-transformers`
  wrapper) — pick whichever is already compatible with the project's
  `uv` lockfile with least new dependency weight; record the choice in
  `DECISIONS.md`.
- `make ingest-kb` is **not run in CI**, mirroring the Day 6 rule ("CI'da
  LLM yok, ETL yok"): it needs local model weights (~2 GB download) with
  no guaranteed CI runtime. Unit tests for the chunker and hasher use
  fixture text with a mocked/stubbed embedding, not the real model; the
  real `make ingest-kb` run against `kb/` is a local, manual step like
  `make etl`.

## Acceptance criteria (from `docs/PLAN.md` row 32)

- ≥ 25 documents (chunks, not files — see anti-goals).
- Every chunk has `source` and `topic`.
- No duplicate chunks on a second ingest run.
