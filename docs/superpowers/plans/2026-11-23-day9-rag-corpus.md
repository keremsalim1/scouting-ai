# Day 9 — RAG Knowledge Base: Corpus, Chunking, Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Day 9 content pipeline — a `kb/` corpus of ≥25 markdown-note chunks, a heading-based chunker, local bge-m3 embedding, and an idempotent `make ingest-kb` that writes into a new `football.kb_chunks` pgvector table with duplicate detection.

**Architecture:** Three pure modules (`src/football_ai/rag/chunker.py` for frontmatter + heading-based splitting, `hashing.py` for normalize+hash+dedupe, `embeddings.py` for a thin bge-m3 wrapper) feed one orchestration module (`ingest.py`) that a CLI script (`scripts/ingest_kb.py`, wired to `make ingest-kb`) runs against a new migration (`infra/migrations/008_kb.sql`). Mirrors Day 8's posture: pure math/logic separated from the DB-writing script, one `TRUNCATE` + insert transaction, idempotent by construction.

**Tech Stack:** Python 3.12, `uv`, `psycopg[binary]`, `pyyaml` (frontmatter), `sentence-transformers` (new dependency, bge-m3), `pytest` (`db` marker for integration tests), `ruff`.

**Spec:** `docs/superpowers/specs/2026-11-23-day9-rag-corpus-design.md`

## Global Constraints

- Python ≥3.12, managed with `uv`; lint set is `["E","W","F","I","UP","B","SIM","PD","RUF"]` (`pyproject.toml`), line length 100.
- Every script that prints output calls `football_ai.console.force_utf8()` first (Windows cp1254 default breaks on Turkish text).
- DB integration tests use `pytest.mark.db`, connect via `football_ai.data.db.connect`/`readonly_dsn`/`etl_dsn`, and `pytest.skip` on `psycopg.OperationalError` — never fail the whole suite when no DB is up.
- Migrations are plain `.sql` files in `infra/migrations/`, applied in filename order by `scripts/migrate.py`; a new file is picked up automatically, no registration step.
- All DB writes that rebuild a derived table use one transaction: `TRUNCATE` then insert — same idempotency posture as `scripts/etl.py` and `scripts/build_vectors.py`.
- `make ingest-kb` is **not** run in CI and never downloads the real bge-m3 model inside a unit test; all chunker/hashing/ingest-orchestration tests inject a fake embed function.
- bge-m3 dense output dimension is 1024; only the dense vector is persisted this day (sparse/multi-vector discarded).
- `topic` values are fixed by a migration-level check constraint, mirroring `player_vectors_weighting_check` in `infra/migrations/005_similarity.sql`.
- `doc_id` = the markdown filename stem (no extension), not a frontmatter field.
- `content_hash` normalization: strip leading/trailing whitespace, collapse runs of internal whitespace to one space; case and punctuation untouched.
- `kb/` notes are hand-written by the project author, summarizing known public sources in the author's own words — no scraping, no LLM-generated factual claims about this project's own data (those come from `metrics.yaml`/`CLAUDE.md` directly).
- Next decision number is **D-034** (`DECISIONS.md` currently ends at D-033).

## Review Focus

- **Heading immediately followed by another heading (empty section):** a reasonable builder expects no empty-content chunk to reach the database. Covered in Task 2.
- **Markdown file missing a required frontmatter field (`title`/`topic`/`source`):** should raise a clear, named error during ingest, not silently store `None`/empty string. Covered in Task 2.
- **Running `make ingest-kb` twice unchanged:** must not duplicate rows and must not raise on re-encountering the same `(doc_id, content_hash)`. Covered in Task 5.
- **Two chunks differing only by trailing whitespace/blank lines:** must hash identically and collapse to one row, per the normalization rule. Covered in Task 3.
- **A section over ~500 words under one heading:** must split further at a paragraph boundary, not become one oversized chunk. Covered in Task 2.

---

## File Structure

- `infra/migrations/008_kb.sql` — new `football.kb_chunks` table, topic check constraint, grant to `football_ro`.
- `src/football_ai/rag/__init__.py` — empty package marker.
- `src/football_ai/rag/chunker.py` — `ParsedDoc`, `parse_frontmatter()`, `Chunk`, `chunk_markdown()`. Pure, no DB, no I/O.
- `src/football_ai/rag/hashing.py` — `normalize_for_hash()`, `content_hash()`, `dedupe_rows()`. Pure.
- `src/football_ai/rag/embeddings.py` — `Embedder` class wrapping `sentence_transformers.SentenceTransformer("BAAI/bge-m3")`, lazy-loaded.
- `src/football_ai/rag/ingest.py` — `load_kb_documents()`, `build_rows()`, `ingest()` orchestration; depends on `chunker`, `hashing`; takes an injected `embed_fn`.
- `scripts/ingest_kb.py` — CLI entry point wired to `make ingest-kb`; the only place that constructs the real `Embedder` and calls `etl_dsn()`.
- `kb/*.md` — 22 content notes (Task 6).
- `tests/test_rag_chunker.py`, `tests/test_rag_hashing.py`, `tests/test_rag_embeddings.py`, `tests/test_rag_ingest.py` (pure/mocked) and `tests/test_rag_ingest_db.py` (DB integration, `pytest.mark.db`).
- `Makefile` — add `ingest-kb:` target.
- `DECISIONS.md` — new `D-034` entry (Task 7).

---

### Task 1: `kb_chunks` migration

**Files:**
- Create: `infra/migrations/008_kb.sql`
- Test: `tests/test_rag_migration_db.py`

**Interfaces:**
- Produces: table `football.kb_chunks(id bigint identity pk, doc_id text, chunk_index integer, topic text, source text, title text, content text, content_hash text, embedding vector(1024), built_at timestamptz)`, unique `(doc_id, content_hash)`, check constraint `kb_chunks_topic_check` on the 22 fixed topic values below, index on `topic`, `select` granted to `football_ro`.

Fixed topic values for the check constraint (exact list — one per `kb/` note planned in Task 6):
`'shooting', 'creation', 'passing', 'progression', 'defending', 'duels', 'discipline', 'goalkeeping', 'per90_normalization', 'minutes_threshold', 'percentile_methodology', 'possession_adjustment', 'position_groups', 'similarity_meaning', 'zscore_cosine', 'xg_regression', 'sample_warnings', 'openplay_data_model', 'season_vs_club', 'possession_proxy', 'data_quality_policy', 'metric_glossary'`

- [ ] **Step 1: Write the failing DB test**

```python
# tests/test_rag_migration_db.py
from __future__ import annotations

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_kb_chunks_has_expected_columns(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'football' and table_name = 'kb_chunks'"
        )
        columns = {row[0] for row in cur.fetchall()}
    assert {
        "doc_id",
        "chunk_index",
        "topic",
        "source",
        "title",
        "content",
        "content_hash",
        "embedding",
        "built_at",
    } <= columns


def test_kb_chunks_rejects_unknown_topic(ro_conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        with ro_conn.cursor() as cur:
            cur.execute(
                "insert into football.kb_chunks "
                "(doc_id, chunk_index, topic, source, title, content, "
                "content_hash, embedding, built_at) "
                "values ('x', 0, 'not_a_real_topic', 's', 't', 'c', 'h', "
                "array_fill(0.0, array[1024])::vector, now())"
            )
    ro_conn.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rag_migration_db.py -v -m db`
Expected: FAIL (`kb_chunks` does not exist) or SKIP if no DB — if SKIP, start the DB (`make db-up`) and re-run.

- [ ] **Step 3: Write `infra/migrations/008_kb.sql`**

Mirror `infra/migrations/005_similarity.sql`'s header-comment style (why a table, why this constraint) and `006_vector_threshold.sql`'s grant pattern. Use `bigint generated always as identity` for `id`, `vector(1024)` for `embedding`.

- [ ] **Step 4: Apply the migration and run test to verify it passes**

Run: `make migrate` then `pytest tests/test_rag_migration_db.py -v -m db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infra/migrations/008_kb.sql tests/test_rag_migration_db.py
git commit -m "feat(rag): add kb_chunks table with topic check constraint"
```

---

### Task 2: Frontmatter parsing + heading-based chunker (pure)

**Files:**
- Create: `src/football_ai/rag/__init__.py`
- Create: `src/football_ai/rag/chunker.py`
- Test: `tests/test_rag_chunker.py`

**Interfaces:**
- Produces:
  - `ParsedDoc` (dataclass): `title: str`, `topic: str`, `source: str`, `body: str`
  - `parse_frontmatter(markdown_text: str) -> ParsedDoc` — raises `FrontmatterError(Exception)` (new, defined in this file) if `title`, `topic`, or `source` is missing.
  - `Chunk` (dataclass): `chunk_index: int`, `content: str`
  - `chunk_markdown(body: str, max_words: int = 500) -> list[Chunk]` — splits on lines starting with `## `; within a section over `max_words` words, splits further at the nearest blank-line (paragraph) boundary; drops any chunk whose stripped content is empty (covers the "heading immediately followed by another heading" case).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rag_chunker.py
from __future__ import annotations

import pytest

from football_ai.rag.chunker import (
    Chunk,
    FrontmatterError,
    ParsedDoc,
    chunk_markdown,
    parse_frontmatter,
)


def test_parse_frontmatter_extracts_title_topic_source():
    text = (
        "---\ntitle: Şut üretimi\ntopic: shooting\nsource: proje notu\n---\n"
        "## Giriş\nİçerik burada.\n"
    )
    doc = parse_frontmatter(text)
    assert doc == ParsedDoc(
        title="Şut üretimi",
        topic="shooting",
        source="proje notu",
        body="## Giriş\nİçerik burada.\n",
    )


def test_parse_frontmatter_missing_field_raises():
    text = "---\ntitle: X\ntopic: shooting\n---\nbody\n"
    with pytest.raises(FrontmatterError):
        parse_frontmatter(text)


def test_chunk_markdown_splits_on_headings():
    body = "## Bir\npara one.\n\n## İki\npara two.\n"
    chunks = chunk_markdown(body)
    assert [c.content.strip() for c in chunks] == ["## Bir\npara one.", "## İki\npara two."]
    assert [c.chunk_index for c in chunks] == [0, 1]


def test_chunk_markdown_drops_empty_section():
    body = "## Bir\n\n## İki\ncontent.\n"
    chunks = chunk_markdown(body)
    assert len(chunks) == 1
    assert "İki" in chunks[0].content


def test_chunk_markdown_splits_oversized_section_at_paragraph_boundary():
    long_para_a = " ".join(["kelime"] * 300)
    long_para_b = " ".join(["farklı"] * 300)
    body = f"## Büyük\n{long_para_a}\n\n{long_para_b}\n"
    chunks = chunk_markdown(body, max_words=400)
    assert len(chunks) == 2
    assert "kelime" in chunks[0].content
    assert "farklı" in chunks[1].content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag_chunker.py -v`
Expected: FAIL with `ModuleNotFoundError: football_ai.rag`

- [ ] **Step 3: Implement `parse_frontmatter` and `chunk_markdown` in `src/football_ai/rag/chunker.py`**

Use `yaml.safe_load` on the text between the first pair of `---` lines (mirror the style, not the code, of `football_ai.metrics`'s validated-load approach). For `chunk_markdown`: split `body` into sections at lines matching `^## `, keeping the heading line as part of the following section's content; for any section whose word count exceeds `max_words`, split at the first blank-line boundary at or after the midpoint word count, recursing if a half is still oversized.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_chunker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/rag/__init__.py src/football_ai/rag/chunker.py tests/test_rag_chunker.py
git commit -m "feat(rag): add frontmatter parser and heading-based chunker"
```

---

### Task 3: Hashing and dedupe (pure)

**Files:**
- Create: `src/football_ai/rag/hashing.py`
- Test: `tests/test_rag_hashing.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure, standalone).
- Produces:
  - `normalize_for_hash(text: str) -> str`
  - `content_hash(text: str) -> str` — `hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()`
  - `dedupe_rows(rows: list[dict], *, key: Callable[[dict], tuple]) -> tuple[list[dict], int]` — returns `(deduped_rows, duplicate_count)`, keeping the first occurrence of each `key(row)` value.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rag_hashing.py
from __future__ import annotations

from football_ai.rag.hashing import content_hash, dedupe_rows, normalize_for_hash


def test_normalize_collapses_internal_whitespace_and_strips_edges():
    assert normalize_for_hash("  a   b\n\nc  ") == "a b c"


def test_content_hash_same_after_whitespace_only_change():
    assert content_hash("a   b") == content_hash("a\nb")


def test_content_hash_differs_on_real_change():
    assert content_hash("a b") != content_hash("a c")


def test_dedupe_rows_keeps_first_and_counts_duplicates():
    rows = [
        {"doc_id": "x", "content_hash": "h1", "n": 1},
        {"doc_id": "x", "content_hash": "h1", "n": 2},
        {"doc_id": "x", "content_hash": "h2", "n": 3},
    ]
    deduped, dup_count = dedupe_rows(rows, key=lambda r: (r["doc_id"], r["content_hash"]))
    assert deduped == [rows[0], rows[2]]
    assert dup_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag_hashing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/football_ai/rag/hashing.py`**

`normalize_for_hash`: `" ".join(text.split())` (splits on all whitespace, strips, collapses in one call). `content_hash`: sha256 hexdigest as specified. `dedupe_rows`: iterate once, track seen keys in a `set`, append first occurrence, count skips.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_hashing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/rag/hashing.py tests/test_rag_hashing.py
git commit -m "feat(rag): add content hashing and duplicate-row detection"
```

---

### Task 4: bge-m3 embedder wrapper

**Files:**
- Create: `src/football_ai/rag/embeddings.py`
- Test: `tests/test_rag_embeddings.py`
- Modify: `pyproject.toml` (add `sentence-transformers` dependency)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Embedder` class with `__init__(self, model: Any | None = None)` (lazy-loads `sentence_transformers.SentenceTransformer("BAAI/bge-m3")` on first `embed()` call if `model` is `None`) and `embed(self, texts: list[str]) -> np.ndarray` returning shape `(len(texts), 1024)`, `dtype=float32`. Later tasks (`ingest.py`) depend only on the `embed_fn: Callable[[list[str]], np.ndarray]` shape, so any object with an `.embed()` method or a bare function satisfies it.

- [ ] **Step 1: Write the failing test with an injected fake model**

```python
# tests/test_rag_embeddings.py
from __future__ import annotations

import numpy as np

from football_ai.rag.embeddings import Embedder


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return np.zeros((len(texts), 1024), dtype=np.float32)


def test_embed_returns_expected_shape_and_dtype():
    embedder = Embedder(model=_FakeModel())
    out = embedder.embed(["a", "b"])
    assert out.shape == (2, 1024)
    assert out.dtype == np.float32


def test_embed_does_not_load_real_model_when_fake_injected():
    # No network/model-download access in this test process; passing a fake
    # model and getting a correct-shaped result proves the real model was
    # never touched.
    embedder = Embedder(model=_FakeModel())
    assert embedder.embed([]).shape == (0, 1024)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add `sentence-transformers` to `pyproject.toml` dependencies and run `uv lock`**

Run: `uv add sentence-transformers`

- [ ] **Step 4: Implement `Embedder` in `src/football_ai/rag/embeddings.py`**

`__init__` stores `model` as-is (no import of `sentence_transformers` at module load time — import it lazily inside a `_load_model()` helper, called only when `self.model is None` and `embed()` is first invoked, so importing this module never requires the package to be installed in a minimal test environment... but note `sentence-transformers` is now a hard dependency, so this is a style choice for import-time cost, not a correctness requirement). `embed` calls `self.model.encode(texts, normalize_embeddings=True)` and casts to `np.float32`; empty input returns `np.zeros((0, 1024), dtype=np.float32)` without calling `.encode()`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_rag_embeddings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/football_ai/rag/embeddings.py tests/test_rag_embeddings.py
git commit -m "feat(rag): add bge-m3 embedder wrapper"
```

---

### Task 5: Ingest orchestration + idempotent DB write

**Files:**
- Create: `src/football_ai/rag/ingest.py`
- Test: `tests/test_rag_ingest.py` (pure/mocked), `tests/test_rag_ingest_db.py` (`pytest.mark.db`)

**Interfaces:**
- Consumes: `ParsedDoc`, `Chunk`, `parse_frontmatter`, `chunk_markdown` from Task 2; `content_hash`, `dedupe_rows` from Task 3; an `embed_fn: Callable[[list[str]], np.ndarray]` matching `Embedder.embed`'s signature from Task 4.
- Produces:
  - `load_kb_documents(kb_dir: Path) -> dict[str, ParsedDoc]` — maps `doc_id` (filename stem) to its parsed document, for every `*.md` file in `kb_dir`.
  - `build_rows(doc_id: str, doc: ParsedDoc) -> list[dict]` — chunks `doc.body`, returns one dict per chunk with keys `doc_id, chunk_index, topic, source, title, content, content_hash` (no `embedding` yet).
  - `IngestResult` (dataclass): `total_chunks: int`, `duplicate_chunks_skipped: int`, `documents: int`.
  - `ingest(conn: psycopg.Connection, kb_dir: Path, embed_fn: Callable[[list[str]], np.ndarray]) -> IngestResult` — loads all docs, builds all rows, dedupes across the whole corpus by `(doc_id, content_hash)`, embeds the surviving rows' `content` in one batch call to `embed_fn`, writes `built_at = datetime.now(UTC)`, then `TRUNCATE football.kb_chunks` + bulk insert in one transaction.

- [ ] **Step 1: Write the failing pure tests**

```python
# tests/test_rag_ingest.py
from __future__ import annotations

from pathlib import Path

from football_ai.rag.ingest import build_rows, load_kb_documents
from football_ai.rag.chunker import ParsedDoc


def test_load_kb_documents_maps_filename_stem_to_doc_id(tmp_path: Path):
    (tmp_path / "shooting.md").write_text(
        "---\ntitle: T\ntopic: shooting\nsource: S\n---\n## H\nbody\n",
        encoding="utf-8",
    )
    docs = load_kb_documents(tmp_path)
    assert set(docs) == {"shooting"}
    assert docs["shooting"].topic == "shooting"


def test_build_rows_produces_one_row_per_chunk_with_hash():
    doc = ParsedDoc(title="T", topic="shooting", source="S", body="## H\nbody text\n")
    rows = build_rows("shooting", doc)
    assert len(rows) == 1
    row = rows[0]
    assert row["doc_id"] == "shooting"
    assert row["topic"] == "shooting"
    assert row["source"] == "S"
    assert row["title"] == "T"
    assert "content_hash" in row and len(row["content_hash"]) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `load_kb_documents` and `build_rows` in `src/football_ai/rag/ingest.py`**

`load_kb_documents`: `sorted(kb_dir.glob("*.md"))`, `path.stem` as key, `parse_frontmatter(path.read_text(encoding="utf-8"))` as value. `build_rows`: `chunk_markdown(doc.body)`, map each `Chunk` to the row dict using `content_hash(chunk.content)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing DB test for idempotent, deduped `ingest()`**

```python
# tests/test_rag_ingest_db.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn
from football_ai.rag.ingest import ingest

pytestmark = pytest.mark.db


def _fake_embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 1024), dtype=np.float32)


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ntopic: shooting\nsource: S\n---\n## H1\nbody one\n## H2\nbody two\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def etl_conn():
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    yield connection
    connection.close()


def test_ingest_is_idempotent_on_repeat_runs(etl_conn, kb_dir):
    first = ingest(etl_conn, kb_dir, _fake_embed)
    second = ingest(etl_conn, kb_dir, _fake_embed)
    assert first.total_chunks == second.total_chunks == 2
    assert first.duplicate_chunks_skipped == 0
    with etl_conn.cursor() as cur:
        cur.execute("select count(*) from football.kb_chunks")
        assert cur.fetchone()[0] == 2


def test_ingest_skips_exact_duplicate_chunks_within_corpus(etl_conn, tmp_path):
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ntopic: shooting\nsource: S\n---\n## H\nsame body\n",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        "---\ntitle: B\ntopic: creation\nsource: S\n---\n## H\nsame body\n",
        encoding="utf-8",
    )
    result = ingest(etl_conn, tmp_path, _fake_embed)
    # different doc_id means these are NOT duplicates of each other (unique key
    # is (doc_id, content_hash)) - both rows persist.
    assert result.total_chunks == 2
    assert result.duplicate_chunks_skipped == 0
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_rag_ingest_db.py -v -m db`
Expected: FAIL (`ingest` not defined) or SKIP if no DB.

- [ ] **Step 7: Implement `ingest()` in `src/football_ai/rag/ingest.py`**

Load all docs, `build_rows` for each, flatten into one list, `dedupe_rows(rows, key=lambda r: (r["doc_id"], r["content_hash"]))`, call `embed_fn([r["content"] for r in deduped])`, zip embeddings onto rows, open a transaction: `TRUNCATE football.kb_chunks`, bulk `INSERT` (use `psycopg.extras`-free `executemany` or a single multi-row `INSERT ... VALUES` built with `psycopg.sql`, matching the style already used in `scripts/etl.py`'s `COPY`/insert code — check that file for the project's preferred bulk-insert idiom before choosing), commit. Return `IngestResult(total_chunks=len(deduped), duplicate_chunks_skipped=len(rows) - len(deduped), documents=len(docs))`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_rag_ingest_db.py -v -m db`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/football_ai/rag/ingest.py tests/test_rag_ingest.py tests/test_rag_ingest_db.py
git commit -m "feat(rag): add idempotent kb ingest orchestration"
```

---

### Task 6: CLI script + Makefile target

**Files:**
- Create: `scripts/ingest_kb.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `ingest()` and `IngestResult` from Task 5, `Embedder` from Task 4, `connect`/`etl_dsn` from `football_ai.data.db`, `force_utf8` from `football_ai.console`.
- Produces: a runnable script printing `IngestResult` fields, exit code 0 on success.

- [ ] **Step 1: Implement `scripts/ingest_kb.py`**

```python
"""Ingest kb/*.md into football.kb_chunks.

    uv run python scripts/ingest_kb.py

Full rebuild in one transaction (TRUNCATE then insert), same idempotency
posture as scripts/etl.py and scripts/build_vectors.py.
"""

from __future__ import annotations

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, connect, etl_dsn
from football_ai.rag.embeddings import Embedder
from football_ai.rag.ingest import ingest

KB_DIR = REPO_ROOT / "kb"


def main() -> None:
    force_utf8()
    conn = connect(etl_dsn())
    embedder = Embedder()
    result = ingest(conn, KB_DIR, embedder.embed)
    print(
        f"documents={result.documents} total_chunks={result.total_chunks} "
        f"duplicates_skipped={result.duplicate_chunks_skipped}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the Makefile target**

Insert next to `build-vectors` (`Makefile:102-104`):

```makefile
ingest-kb:
	$(UV) run python scripts/ingest_kb.py
```

- [ ] **Step 3: Verify manually (no kb/ content yet, expect 0 chunks)**

Run: `make migrate && make ingest-kb`
Expected: prints `documents=0 total_chunks=0 duplicates_skipped=0`, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/ingest_kb.py Makefile
git commit -m "feat(rag): wire make ingest-kb to the ingest pipeline"
```

---

### Task 7: Write the 22 `kb/` notes and measure the acceptance criteria

**Files:**
- Create: 22 files under `kb/`, one per topic below. Filename = `kb/<topic-with-hyphens>.md` (e.g. `kb/per90-normalization.md`); `doc_id` will be the stem (`per90-normalization`), independent of the `topic` frontmatter field's underscore form.
- Modify: `DECISIONS.md` (append `D-034`).

**Topic → filename → frontmatter `topic` value (must match Task 1's check constraint exactly):**

| Group | Filename | `topic` |
| --- | --- | --- |
| A | `kb/shooting.md` | `shooting` |
| A | `kb/creation.md` | `creation` |
| A | `kb/passing.md` | `passing` |
| A | `kb/progression.md` | `progression` |
| A | `kb/defending.md` | `defending` |
| A | `kb/duels.md` | `duels` |
| A | `kb/discipline.md` | `discipline` |
| A | `kb/goalkeeping.md` | `goalkeeping` |
| B | `kb/per90-normalization.md` | `per90_normalization` |
| B | `kb/minutes-threshold.md` | `minutes_threshold` |
| B | `kb/percentile-methodology.md` | `percentile_methodology` |
| B | `kb/possession-adjustment.md` | `possession_adjustment` |
| B | `kb/position-groups.md` | `position_groups` |
| B | `kb/similarity-meaning.md` | `similarity_meaning` |
| B | `kb/zscore-cosine.md` | `zscore_cosine` |
| B | `kb/xg-regression.md` | `xg_regression` |
| B | `kb/sample-warnings.md` | `sample_warnings` |
| C | `kb/openplay-data-model.md` | `openplay_data_model` |
| C | `kb/season-vs-club.md` | `season_vs_club` |
| C | `kb/possession-proxy.md` | `possession_proxy` |
| C | `kb/data-quality-policy.md` | `data_quality_policy` |
| C | `kb/metric-glossary.md` | `metric_glossary` |

Each file: YAML frontmatter (`title`, `topic`, `source`) + at least one `## ` heading with real content, summarized from known public scouting/analytics sources (StatsBomb/FBref-style glossaries, general tactical-analysis writing) in the author's own words for groups A/B, and from this project's own `config/metrics.yaml`/`CLAUDE.md` facts for group C. `kb/metric-glossary.md` should cover all 38 metrics from `config/metrics.yaml`, one line each, grouped under one `##` heading per category (this is the file expected to produce the most chunks after the ~500-word paragraph split, per the spec's "measured, not guaranteed" approach to the 25-chunk threshold).

- [ ] **Step 1: Write all 22 files per the table above**

- [ ] **Step 2: Run `make ingest-kb` and record the result**

Run: `make migrate && make ingest-kb`
Expected: `documents=22 total_chunks=N duplicates_skipped=0` where `N >= 25`. If `N < 25`, split `kb/metric-glossary.md` (or another note) into more `##` sections and re-run — do not change the chunker to force a count.

- [ ] **Step 3: Write the DB verification query**

Run (via `make db-shell` or any psql client):
```sql
select topic, source is not null, title is not null from football.kb_chunks limit 5;
select count(*), count(distinct content_hash) from football.kb_chunks;
```
Expected: every row has non-null `source`/`title`; `count(*)` matches Step 2's `total_chunks` (confirms "kopya yok" — no duplicate rows from a single ingest).

- [ ] **Step 4: Append `DECISIONS.md` entry `D-034`**

Record: the bge-m3-via-sentence-transformers choice (dense-only this day), the topic check-constraint approach, the measured chunk count from Step 2, and the three content groups (A/B/C) with their rationale — following the existing `## D-XXX: Title` → Bağlam/Karar/Alternatifler/Sonuç-ölçüm/Tarih format already used for D-001…D-033.

- [ ] **Step 5: Update `CLAUDE.md`'s "Durum" checklist**

Mark Day 9 `[x]` with the measured chunk count and document count, matching the style of the Day 7/Day 8 entries already there.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass (including the new `tests/test_rag_*` files and the pre-existing suite).

- [ ] **Step 7: Commit**

```bash
git add kb/ DECISIONS.md CLAUDE.md
git commit -m "docs(rag): add 22 kb methodology/glossary notes, record D-034"
```

---

## Self-Review

**1. Spec coverage:** Group A/B/C corpus → Task 7. Heading-based chunker, paragraph split → Task 2. bge-m3 local dense embedding → Task 4. `kb_chunks` table + check constraint → Task 1. `make ingest-kb`, dedupe, idempotent `TRUNCATE`+insert → Tasks 5–6. `content_hash` normalization → Task 3. `doc_id` = filename stem → Task 5 (`load_kb_documents`). CI/mocking posture → Global Constraints + every embedding-dependent test uses a fake. D-034 + `CLAUDE.md` update → Task 7. All spec sections covered.

**2. Step scan:** checked — no step says "handle edge cases" or leaves a type undefined; Task 5 Step 7's bulk-insert idiom is deliberately left as "check the project's existing style" rather than dictated, since `scripts/etl.py`'s idiom wasn't inspected while writing this plan and the implementer can see it directly.

**3. Type consistency:** `embed_fn: Callable[[list[str]], np.ndarray]` is used consistently in Tasks 4 and 5; `Embedder.embed` matches that shape. `ParsedDoc`/`Chunk` fields are referenced identically across Tasks 2 and 5. `IngestResult` fields (`total_chunks`, `duplicate_chunks_skipped`, `documents`) are used consistently in Tasks 5–7.

**4. Review Focus:** all five listed failure modes map to a task's tests (empty section → Task 2; missing frontmatter field → Task 2; repeat-run duplication → Task 5; whitespace-only hash collision → Task 3; oversized section split → Task 2).

**5. Proportion:** plan is longer than the spec because it carries exact test code for seven tasks across a brand-new subsystem (no prior `rag/` code to point at); each test block is short and code-light relative to a full spec-to-code transcript, and Task 7 — the largest content item — deliberately carries no prose, only a filename/topic table.
