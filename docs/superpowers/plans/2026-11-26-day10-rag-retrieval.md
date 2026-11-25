# Day 10 — RAG retrieval: hybrid search, RRF, reranking, abstention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 50 dense-embedded rows in `football.kb_chunks` into a `methodology_search` tool that fuses vector and full-text retrieval, reranks with a cross-encoder, cites every passage, and returns nothing when the question is not covered by the corpus.

**Architecture:** Four pure-ish layers under `src/football_ai/rag/`, each independently testable with fakes, composed by one orchestrator. `config.py` loads `config/rag.yaml` (parameters, thresholds). `search.py` runs the two retrievers against Postgres and returns ranked `Hit` lists. `fusion.py` combines them by rank only (RRF). `rerank.py` wraps `bge-reranker-v2-m3` behind the same lazy-import, injectable-model posture as Day 9's `Embedder`. `retrieval.py` composes them, truncating the pipeline per mode (`dense` / `hybrid` / `hybrid_rerank`) and applying the mode's abstention check. No LLM call anywhere; both models run locally on CPU.

**Tech Stack:** Python 3.12, psycopg 3, pgvector, Postgres full-text (`tsvector` / `websearch_to_tsquery` / `ts_rank`), `sentence-transformers` (`CrossEncoder`), Pydantic, pytest, numpy, PyYAML.

**Spec:** `docs/superpowers/specs/2026-11-26-day10-rag-retrieval-design.md`

## Global Constraints

- No paid API call anywhere in this layer; both models run locally (student budget, ~$5 total).
- CI runs no LLM, no ETL, no model download. Unit tests inject fake embed/rerank callables; DB tests use synthetic vectors (`tests/test_rag_ingest_db.py` is the pattern).
- Every DB-touching test carries `pytestmark = pytest.mark.db`; `pytest` excludes `data` and `db` by default (`pyproject.toml:70`).
- Everything in this layer must run as `football_ro` (read-only); Day 13's agent sees only that role.
- Any script that prints calls `football_ai.console.force_utf8()` first.
- Code, comments, identifiers and commit messages in English. Corpus text and user-facing abstain messages are Turkish, matching `kb/`.
- Citation is a schema guarantee, not a convention: `source` and `title` are `not null` in `kb_chunks` and must appear on every returned passage.
- `text_search_config` default is `simple`; `rrf_k` default is `60`.

## Review Focus

Input classes the spec implies but does not give a task; each has a test added to the owning task below.

1. **Empty or whitespace-only query** — must abstain without calling either model or hitting the DB, not raise (Task 6).
2. **A query whose top fused hit is lexical-only** (no dense score) — the hybrid threshold lookup must not `KeyError`; relevance is the best dense similarity over all dense candidates, and with an empty dense list it abstains (Task 6).
3. **`kb_chunks` empty** (migrations applied, `make ingest-kb` never run) — must raise `EmptyCorpusError`, because zero results from an empty corpus is indistinguishable from a correct abstention and would be read as "the corpus doesn't cover this" (Task 6).
4. **Query text containing `tsquery` operators or stray punctuation** (`&`, `|`, `!`, `:`, `"`) — `websearch_to_tsquery` must swallow it rather than erroring; a quoted phrase is a legitimate query, not an injection (Task 2).
5. **Turkish case folding and dotted/dotless i** — `simple` lowercases via the database collation, so `YÜZDELIK` and `yüzdelik` must match the same chunk; this is the specific risk of choosing `simple` over a Turkish dictionary (Task 2).

---

## File Structure

| File | Responsibility |
| --- | --- |
| `config/rag.yaml` | Retrieval parameters and the two abstention thresholds (runtime authority). |
| `src/football_ai/rag/config.py` | Parse + validate that yaml into a frozen `RagConfig`. |
| `infra/migrations/009_kb_fts.sql` | Generated `content_tsv` column, GIN index, grant. |
| `src/football_ai/rag/search.py` | `dense_search`, `lexical_search`, `assert_text_search_config`. |
| `src/football_ai/rag/fusion.py` | `fuse()` — RRF over the two ranked lists, carrying provenance. |
| `src/football_ai/rag/rerank.py` | `Reranker` cross-encoder wrapper, sigmoid-scaled scores. |
| `src/football_ai/rag/retrieval.py` | `methodology_search`, Pydantic result models, abstention, modes. |
| `scripts/kb_search.py` | `make kb-search Q="..." MODE=...` entry point. |
| `scripts/calibrate_abstain.py` | Prints the two score distributions behind the thresholds. |

---

### Task 1: Retrieval configuration

**Files:**
- Create: `config/rag.yaml`
- Create: `src/football_ai/rag/config.py`
- Test: `tests/test_rag_config.py`

**Interfaces:**
- Consumes: `football_ai.data.db.REPO_ROOT`.
- Produces:
  ```python
  RAG_CONFIG_PATH: Path  # REPO_ROOT / "config" / "rag.yaml"
  VALID_MODES: frozenset[str]  # {"dense", "hybrid", "hybrid_rerank"}

  @dataclass(frozen=True)
  class RagConfig:
      version: int
      text_search_config: str
      rrf_k: int
      dense_candidates: int
      lexical_candidates: int
      rerank_candidates: int
      top_n: int
      dense_abstain_threshold: float
      rerank_abstain_threshold: float
      rerank_model: str

  def parse(raw: dict[str, Any]) -> RagConfig
  def load(path: Path = RAG_CONFIG_PATH) -> RagConfig
  ```

- [ ] **Step 1: Write `config/rag.yaml`**

```yaml
version: 1

# Postgres text search configuration. Baked into 009_kb_fts.sql's generated
# column (a stored generated column needs an immutable expression), so this
# value exists to keep the query side in step with the index - changing it
# means a new migration, not just an edit here. `simple` (case folding, no
# stemming) is the day-10 choice for a mixed Turkish/English corpus: a
# Turkish stemmer mangles `higher_is_better`, an English one mangles the
# prose. Day 11 measures it.
text_search_config: simple

# Reciprocal rank fusion constant from the original paper. Large relative to
# the candidate depth, so the curve is gentle and rank 1 does not dominate.
rrf_k: 60

dense_candidates: 20
lexical_candidates: 20

# How many fused candidates reach the cross-encoder. Separate from the two
# retriever depths because fusion can surface up to their sum, and the
# reranker is the expensive stage - this is the number that bounds its cost.
rerank_candidates: 20

top_n: 5

# Abstention thresholds. Placeholders until task 8 measures them; the values
# below are deliberately wrong-looking so an unmeasured threshold cannot be
# mistaken for a measured one.
dense_abstain_threshold: 0.5
rerank_abstain_threshold: 0.5

rerank_model: BAAI/bge-reranker-v2-m3
```

- [ ] **Step 2: Write the failing tests**

```python
def test_load_reads_the_repo_config():
    cfg = load()
    assert cfg.text_search_config == "simple"
    assert cfg.rrf_k == 60
    assert cfg.top_n == 5


def test_parse_rejects_missing_field():
    raw = _valid_raw()
    del raw["rrf_k"]
    with pytest.raises(ValueError, match="rrf_k"):
        parse(raw)


def test_parse_rejects_non_positive_rrf_k():
    with pytest.raises(ValueError, match="rrf_k"):
        parse({**_valid_raw(), "rrf_k": 0})


def test_parse_rejects_top_n_above_candidate_depth():
    # top_n larger than what retrieval can supply is a silent truncation bug
    with pytest.raises(ValueError, match="top_n"):
        parse({**_valid_raw(), "top_n": 50})


def test_parse_rejects_rerank_candidates_below_top_n():
    with pytest.raises(ValueError, match="rerank_candidates"):
        parse({**_valid_raw(), "rerank_candidates": 3, "top_n": 5})


@pytest.mark.parametrize("field", ["dense_abstain_threshold", "rerank_abstain_threshold"])
def test_parse_rejects_threshold_outside_unit_interval(field):
    with pytest.raises(ValueError, match=field):
        parse({**_valid_raw(), field: 1.4})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_config.py -v`
Expected: FAIL, `ModuleNotFoundError: football_ai.rag.config`

- [ ] **Step 4: Implement `parse` and `load` in `src/football_ai/rag/config.py`**

Follow `src/football_ai/metrics.py`'s loader shape: a `_require(mapping, key, where)` helper that raises `ValueError` naming the missing field, then range checks. Validate: all fields present; `rrf_k`, `dense_candidates`, `lexical_candidates`, `rerank_candidates`, `top_n` positive ints; `top_n <= min(dense_candidates, lexical_candidates)` and `top_n <= rerank_candidates`; both thresholds in `[0.0, 1.0]`; `text_search_config` and `rerank_model` non-empty strings.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add config/rag.yaml src/football_ai/rag/config.py tests/test_rag_config.py
git commit -m "feat(rag): add retrieval config with validated thresholds"
```

---

### Task 2: Full-text index and lexical search

**Files:**
- Create: `infra/migrations/009_kb_fts.sql`
- Create: `src/football_ai/rag/search.py`
- Test: `tests/test_rag_fts_db.py`

**Interfaces:**
- Consumes: `RagConfig.text_search_config` (Task 1).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Hit:
      chunk_id: int
      doc_id: str
      chunk_index: int
      topic: str
      source: str
      title: str
      content: str
      score: float   # ts_rank for lexical, cosine similarity for dense
      rank: int      # 1-based position in this retriever's own list

  class TextSearchConfigMismatchError(Exception): ...

  def assert_text_search_config(conn: psycopg.Connection, expected: str) -> None
  def lexical_search(conn: psycopg.Connection, query: str, *, limit: int,
                     text_search_config: str) -> list[Hit]
  ```

- [ ] **Step 1: Write the migration `infra/migrations/009_kb_fts.sql`**

```sql
-- 009_kb_fts.sql
--
-- Day 10: the lexical half of hybrid retrieval. See
-- docs/superpowers/specs/2026-11-26-day10-rag-retrieval-design.md.
--
-- Why a second retriever at all: exact technical terms (`npxg_per_shot`,
-- `player_season_club`, "900 dakika") are where dense embeddings are weakest
-- - to bge-m3, npxG and xA are near-identical - and where lexical matching is
-- strongest. The two retrievers fail on different questions, which is the
-- only reason fusing them helps.
--
-- `simple` (case folding, no stemming) because the corpus is mixed-language:
-- Turkish prose with English identifiers in the same sentence. A stored
-- generated column needs an immutable expression, so the configuration is
-- baked in here rather than read from config/rag.yaml; the retrieval code
-- asserts the two agree. Switching dictionaries is a new migration, which
-- keeps what the index contains visible in the schema (same deliberate
-- friction as 008's topic check constraint).

alter table football.kb_chunks
    add column content_tsv tsvector
    generated always as (
        setweight(to_tsvector('simple', title), 'A')
        || setweight(to_tsvector('simple', content), 'B')
    ) stored;

create index kb_chunks_content_tsv_idx on football.kb_chunks using gin (content_tsv);

comment on column football.kb_chunks.content_tsv is
    'Lexical half of day 10 hybrid retrieval. Title weighted A, body B, so a '
    'heading match outranks an incidental body mention of the same term.';
```

`grant select on football.kb_chunks to football_ro` in `008_kb.sql` is table-level and already covers the new column; no new grant.

- [ ] **Step 2: Write the failing tests**

```python
pytestmark = pytest.mark.db


def test_assert_text_search_config_accepts_the_migrated_config(ro_conn):
    assert_text_search_config(ro_conn, "simple")  # does not raise


def test_assert_text_search_config_rejects_a_different_config(ro_conn):
    with pytest.raises(TextSearchConfigMismatchError, match="turkish"):
        assert_text_search_config(ro_conn, "turkish")


def test_lexical_search_finds_an_exact_technical_term(ro_conn):
    hits = lexical_search(ro_conn, "player_season_club", limit=5, text_search_config="simple")
    assert hits
    assert any("season-vs-club" == h.doc_id for h in hits)
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
    assert all(h.source and h.title for h in hits)


def test_lexical_search_is_case_insensitive_for_turkish_text(ro_conn):
    lower = lexical_search(ro_conn, "yüzdelik", limit=5, text_search_config="simple")
    upper = lexical_search(ro_conn, "YÜZDELIK", limit=5, text_search_config="simple")
    assert [h.chunk_id for h in lower] == [h.chunk_id for h in upper]
    assert lower


def test_lexical_search_survives_tsquery_operators(ro_conn):
    hits = lexical_search(
        ro_conn, 'yüzdelik & | ! "orta-sıra":', limit=5, text_search_config="simple"
    )
    assert all(h.rank >= 1 for h in hits)  # no exception, well-formed ranks


def test_lexical_search_returns_empty_for_a_term_not_in_the_corpus(ro_conn):
    assert lexical_search(ro_conn, "zzzqqq", limit=5, text_search_config="simple") == []
```

The `ro_conn` fixture mirrors `tests/test_rag_ingest_db.py`'s `etl_conn` but uses `connect(readonly_dsn())`, skipping on `psycopg.OperationalError`. These tests read the real ingested corpus, so they also skip when `kb_chunks` is empty.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_fts_db.py -v -m db`
Expected: FAIL, `ModuleNotFoundError: football_ai.rag.search`

- [ ] **Step 4: Apply the migration**

Run: `make migrate`
Expected: `009_kb_fts` applied; existing 50 rows get `content_tsv` populated by the stored generated column with no re-ingest.

- [ ] **Step 5: Implement `search.py`'s lexical half**

`lexical_search` runs one query with `psycopg.rows.dict_row`, `websearch_to_tsquery(%s, %s)` (not `to_tsquery` — it accepts arbitrary user text without raising on operators), ordering by `ts_rank(content_tsv, query) desc, id`, with `limit`; the tie-breaking `id` keeps the rank list deterministic. Return `Hit`s with `rank` assigned by enumeration. Pass `text_search_config` as a parameter, never interpolated.

`assert_text_search_config` reads the generated column's expression via `pg_get_expr(d.adbin, d.adrelid)` joined from `pg_attrdef` to `pg_attribute` for `('football.kb_chunks'::regclass, 'content_tsv')`, and raises `TextSearchConfigMismatchError` naming both configs unless `f"'{expected}'::regconfig"` appears in it. A silently differently-stemmed search is worse than a crash: it returns plausible wrong passages.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_fts_db.py -v -m db`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add infra/migrations/009_kb_fts.sql src/football_ai/rag/search.py tests/test_rag_fts_db.py
git commit -m "feat(rag): add kb full-text index and lexical search"
```

---

### Task 3: Dense search

**Files:**
- Modify: `src/football_ai/rag/search.py`
- Create: `tests/test_rag_dense_db.py`

**Interfaces:**
- Consumes: `Hit` (Task 2).
- Produces:
  ```python
  class EmptyCorpusError(Exception): ...
  def dense_search(conn: psycopg.Connection, embedding: np.ndarray, *,
                   limit: int) -> list[Hit]
  ```

- [ ] **Step 1: Write the failing tests**

```python
pytestmark = pytest.mark.db


def test_dense_search_ranks_by_similarity_descending(ro_conn, embedder):
    hits = dense_search(ro_conn, embedder.embed(["yüzdelik nasıl hesaplanıyor"])[0], limit=10)
    assert len(hits) == 10
    assert [h.rank for h in hits] == list(range(1, 11))
    assert hits == sorted(hits, key=lambda h: -h.score)
    assert all(-1.0 <= h.score <= 1.0 for h in hits)
    assert all(h.source and h.title for h in hits)


def test_dense_search_respects_the_limit(ro_conn, embedder):
    assert len(dense_search(ro_conn, embedder.embed(["pas isabeti"])[0], limit=3)) == 3
```

`embedder` is a module-scoped fixture returning the real `Embedder()`; it skips when `sentence_transformers` or the model cache is unavailable, so CI never downloads a model. `EmptyCorpusError` is raised here but asserted in Task 6's DB test, which already truncates `kb_chunks` inside a rolled-back transaction — duplicating that setup here would be a second way to get the same assurance.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_dense_db.py -v -m db`
Expected: FAIL, `ImportError: cannot import name 'dense_search'`

- [ ] **Step 3: Implement `dense_search`**

One query ordering by `embedding <=> %s::vector` ascending with `limit`, selecting `1 - (embedding <=> %s::vector) as score` so the returned score is cosine *similarity* (higher is better, consistent with `ts_rank` and the reranker, so every `Hit.score` in the codebase points the same way). Serialize the vector as a bracketed string (`"[" + ",".join(...) + "]"`), the format `scripts/build_vectors.py` already uses. Raise `EmptyCorpusError` when the query returns zero rows, with a message naming `make ingest-kb`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_dense_db.py -v -m db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/rag/search.py tests/test_rag_dense_db.py
git commit -m "feat(rag): add dense kb search over pgvector"
```

---

### Task 4: Reciprocal rank fusion

**Files:**
- Create: `src/football_ai/rag/fusion.py`
- Test: `tests/test_rag_fusion.py`

**Interfaces:**
- Consumes: `Hit` (Task 2).
- Produces:
  ```python
  @dataclass(frozen=True)
  class FusedHit:
      hit: Hit                        # whichever retriever saw it first; identical content either way
      rrf_score: float
      dense_rank: int | None
      dense_similarity: float | None
      lexical_rank: int | None
      lexical_score: float | None

  def fuse(dense: Sequence[Hit], lexical: Sequence[Hit], *, k: int) -> list[FusedHit]
  ```
  Explicitly two named arguments rather than a generic list of lists: the provenance fields are how a consumer answers "why was this returned", and a generic fuser cannot label them.

- [ ] **Step 1: Write the failing tests**

```python
def test_fuse_scores_a_hit_in_both_lists_higher_than_either_alone():
    # a: dense 1, lexical 3 -> 1/61 + 1/63 ; b: dense 2 only -> 1/62
    fused = fuse([_hit(1, "a"), _hit(2, "b")], [_hit(1, "c"), _hit(2, "d"), _hit(3, "a")], k=60)
    assert fused[0].hit.doc_id == "a"
    assert fused[0].rrf_score == pytest.approx(1 / 61 + 1 / 63)


def test_fuse_carries_both_ranks_and_both_scores():
    fused = fuse([_hit(1, "a", score=0.8)], [_hit(1, "a", score=0.02)], k=60)
    only = fused[0]
    assert (only.dense_rank, only.lexical_rank) == (1, 1)
    assert (only.dense_similarity, only.lexical_score) == (0.8, 0.02)


def test_fuse_leaves_the_other_retrievers_fields_none_for_a_single_list_hit():
    fused = fuse([_hit(1, "a")], [], k=60)
    assert fused[0].lexical_rank is None and fused[0].lexical_score is None
    assert fused[0].dense_rank == 1


def test_fuse_of_two_empty_lists_is_empty():
    assert fuse([], [], k=60) == []


def test_fuse_ignores_score_magnitude_entirely():
    # ts_rank is unbounded and cosine is not; fusion must read ranks only
    a = fuse([_hit(1, "a", score=0.9)], [_hit(1, "b", score=0.01)], k=60)
    b = fuse([_hit(1, "a", score=0.9)], [_hit(1, "b", score=99.0)], k=60)
    assert [h.hit.doc_id for h in a] == [h.hit.doc_id for h in b]


def test_fuse_is_deterministic_on_tied_scores():
    fused = fuse([_hit(1, "b"), _hit(2, "a")], [_hit(1, "a"), _hit(2, "b")], k=60)
    assert [h.hit.doc_id for h in fused] == ["a", "b"]  # tie broken by chunk_id
```

`_hit(rank, doc_id, score=...)` is a local helper building a `Hit` whose `chunk_id` is derived from `doc_id` so identity across lists is by `chunk_id`, as in production.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_fusion.py -v`
Expected: FAIL, `ModuleNotFoundError: football_ai.rag.fusion`

- [ ] **Step 3: Implement `fuse`**

Group by `Hit.chunk_id`; `rrf_score = Σ 1/(k + rank)` over the lists the chunk appears in; sort by `(-rrf_score, chunk_id)` so ties are deterministic. Returns all fused candidates, unsliced — the caller owns `top_n`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_fusion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/rag/fusion.py tests/test_rag_fusion.py
git commit -m "feat(rag): add reciprocal rank fusion over the two retrievers"
```

---

### Task 5: Cross-encoder reranker

**Files:**
- Create: `src/football_ai/rag/rerank.py`
- Test: `tests/test_rag_rerank.py`

**Interfaces:**
- Produces:
  ```python
  RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

  class Reranker:
      def __init__(self, model: Any | None = None, model_name: str = RERANK_MODEL) -> None
      def score(self, query: str, passages: list[str]) -> np.ndarray  # float32, in [0, 1]
  ```
  `score` is the callable `methodology_search` takes as `rerank_fn`, via `Reranker().score`.

- [ ] **Step 1: Write the failing tests**

```python
class _FakeCrossEncoder:
    def __init__(self, logits):
        self.logits, self.seen = logits, None

    def predict(self, pairs, **kwargs):
        self.seen = pairs
        return np.asarray(self.logits, dtype=np.float32)


def test_score_pairs_the_query_with_every_passage():
    fake = _FakeCrossEncoder([1.0, -2.0])
    Reranker(model=fake).score("q", ["p1", "p2"])
    assert fake.seen == [("q", "p1"), ("q", "p2")]


def test_score_maps_logits_through_a_sigmoid():
    # raw bge-reranker output is an unbounded logit; a threshold in
    # config/rag.yaml has to be a readable number, so it is squashed to [0, 1]
    out = Reranker(model=_FakeCrossEncoder([0.0, 4.0, -4.0])).score("q", ["a", "b", "c"])
    assert out[0] == pytest.approx(0.5)
    assert out[1] > 0.98 and out[2] < 0.02
    assert out.dtype == np.float32


def test_score_preserves_the_order_of_the_logits():
    out = Reranker(model=_FakeCrossEncoder([-1.0, 3.0, 1.0])).score("q", list("abc"))
    assert list(np.argsort(-out)) == [1, 2, 0]


def test_score_of_no_passages_is_an_empty_array_without_loading_a_model():
    out = Reranker().score("q", [])  # no model injected: must not import or download
    assert out.shape == (0,)


def test_score_rejects_a_mismatched_model_output_length():
    with pytest.raises(ValueError, match="2"):
        Reranker(model=_FakeCrossEncoder([1.0])).score("q", ["a", "b"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_rerank.py -v`
Expected: FAIL, `ModuleNotFoundError: football_ai.rag.rerank`

- [ ] **Step 3: Implement `Reranker`**

Copy Day 9 `src/football_ai/rag/embeddings.py`'s structure exactly: injected `model` or a lazily imported `sentence_transformers.CrossEncoder(model_name)` on first use, so importing the module never triggers a download. `score` returns early on an empty `passages` list before touching the model, builds `[(query, p) for p in passages]`, calls `model.predict(...)`, validates the output length against `len(passages)` (a mismatch means the model silently batched something away), and applies `1 / (1 + exp(-x))` via numpy.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_rerank.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/football_ai/rag/rerank.py tests/test_rag_rerank.py
git commit -m "feat(rag): add bge-reranker-v2-m3 cross-encoder wrapper"
```

---

### Task 6: `methodology_search` — modes, abstention, citation

**Files:**
- Create: `src/football_ai/rag/retrieval.py`
- Test: `tests/test_rag_retrieval.py` (fakes, no DB), `tests/test_rag_retrieval_db.py` (real corpus)

**Interfaces:**
- Consumes: `RagConfig`/`load` (Task 1), `Hit`/`dense_search`/`lexical_search`/`assert_text_search_config`/`EmptyCorpusError` (Tasks 2–3), `fuse`/`FusedHit` (Task 4), `Reranker.score` (Task 5).
- Produces:
  ```python
  ABSTAIN_MESSAGE = "Bilgi tabanında bu konuda bilgi yok."

  class Passage(BaseModel):
      doc_id: str; chunk_index: int; topic: str; source: str; title: str; content: str
      dense_rank: int | None = None; dense_similarity: float | None = None
      lexical_rank: int | None = None; lexical_score: float | None = None
      rrf_score: float | None = None; rerank_score: float | None = None

  class MethodologySearchResult(BaseModel):
      query: str; mode: str
      passages: list[Passage]
      abstained: bool
      abstain_reason: str | None
      relevance_signal: str | None   # "dense_similarity" | "rerank_score"
      relevance_score: float | None
      threshold: float | None
      generated_at: datetime

  def methodology_search(
      conn: psycopg.Connection, query: str, *,
      embed_fn: Callable[[list[str]], np.ndarray],
      rerank_fn: Callable[[str, list[str]], np.ndarray] | None = None,
      mode: str = "hybrid_rerank",
      config: RagConfig | None = None,
  ) -> MethodologySearchResult
  ```

- [ ] **Step 1: Write the failing unit tests (fakes, no DB)**

```python
def test_empty_query_abstains_without_calling_the_models(monkeypatch):
    calls = []
    result = methodology_search(
        _conn_that_raises(), "   ", embed_fn=lambda t: calls.append(t) or _vecs(1), mode="dense"
    )
    assert result.abstained and result.passages == []
    assert result.abstain_reason and calls == []


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        methodology_search(_conn(), "q", embed_fn=_embed, mode="rerank_only")


def test_hybrid_rerank_without_a_rerank_fn_is_rejected():
    with pytest.raises(ValueError, match="rerank_fn"):
        methodology_search(_conn(), "q", embed_fn=_embed, mode="hybrid_rerank")


def test_dense_mode_abstains_below_the_similarity_threshold(fake_search):
    fake_search.dense = [_hit(1, "a", score=0.21)]
    result = methodology_search(
        _conn(), "q", embed_fn=_embed, mode="dense", config=_cfg(dense_abstain_threshold=0.5)
    )
    assert result.abstained
    assert (result.relevance_signal, result.relevance_score) == ("dense_similarity", 0.21)
    assert result.threshold == 0.5


def test_dense_mode_returns_top_n_above_the_threshold(fake_search):
    fake_search.dense = [_hit(i, f"d{i}", score=0.9 - i / 100) for i in range(1, 11)]
    result = methodology_search(_conn(), "q", embed_fn=_embed, mode="dense", config=_cfg(top_n=5))
    assert not result.abstained and len(result.passages) == 5
    assert all(p.source and p.title for p in result.passages)
    assert all(p.rrf_score is None and p.rerank_score is None for p in result.passages)


def test_hybrid_mode_scores_relevance_over_all_dense_candidates(fake_search):
    # top fused hit is lexical-only, and the strongest dense hit is not in top_n
    fake_search.dense = [_hit(1, "b", score=0.77)]
    fake_search.lexical = [_hit(1, "a", score=0.03), _hit(2, "b", score=0.01)]
    result = methodology_search(
        _conn(),
        "q",
        embed_fn=_embed,
        mode="hybrid",
        config=_cfg(top_n=1, dense_abstain_threshold=0.5),
    )
    assert not result.abstained  # did not KeyError, did not abstain
    assert result.relevance_score == 0.77
    assert [p.doc_id for p in result.passages] == ["a"]  # ranking unchanged by this


def test_dense_and_hybrid_agree_on_abstention_for_the_same_query(fake_search):
    # the regression this guards: fusion must not be able to flip the abstain
    # decision, or day 11's ablation measures ranking and abstention at once
    fake_search.dense = [_hit(1, "x", score=0.77), _hit(2, "y", score=0.10)]
    fake_search.lexical = [
        _hit(1, "a", score=0.03),
        _hit(2, "b", score=0.02),
        _hit(3, "y", score=0.01),
    ]
    cfg = _cfg(top_n=2, dense_abstain_threshold=0.5)
    both = [
        methodology_search(_conn(), "q", embed_fn=_embed, mode=m, config=cfg)
        for m in ("dense", "hybrid")
    ]
    assert {r.abstained for r in both} == {False}
    assert {r.relevance_score for r in both} == {0.77}


def test_hybrid_mode_abstains_when_the_dense_list_is_empty(fake_search):
    fake_search.dense = []
    fake_search.lexical = [_hit(1, "a", score=0.03)]
    result = methodology_search(_conn(), "q", embed_fn=_embed, mode="hybrid")
    assert result.abstained and result.relevance_score is None


def test_hybrid_rerank_reorders_the_fused_candidates(fake_search):
    fake_search.dense = [_hit(1, "a"), _hit(2, "b")]
    fake_search.lexical = []
    result = methodology_search(
        _conn(),
        "q",
        embed_fn=_embed,
        rerank_fn=lambda q, ps: np.array([0.1, 0.95], dtype=np.float32),
        mode="hybrid_rerank",
        config=_cfg(rerank_abstain_threshold=0.5),
    )
    assert [p.doc_id for p in result.passages] == ["b", "a"]
    assert result.relevance_signal == "rerank_score"
    assert result.relevance_score == pytest.approx(0.95)


def test_hybrid_rerank_abstains_when_the_best_rerank_score_is_low(fake_search):
    fake_search.dense = [_hit(1, "a")]
    result = methodology_search(
        _conn(),
        "q",
        embed_fn=_embed,
        rerank_fn=lambda q, ps: np.array([0.12], dtype=np.float32),
        mode="hybrid_rerank",
        config=_cfg(rerank_abstain_threshold=0.5),
    )
    assert result.abstained and result.passages == []
    assert ABSTAIN_MESSAGE in result.abstain_reason


def test_reranker_sees_only_the_fused_candidates_not_the_whole_corpus(fake_search):
    fake_search.dense = [_hit(i, f"d{i}") for i in range(1, 31)]
    seen = {}
    methodology_search(
        _conn(),
        "q",
        embed_fn=_embed,
        rerank_fn=lambda q, ps: (
            seen.setdefault("n", len(ps)) and np.ones(len(ps), dtype=np.float32)
        ),
        mode="hybrid_rerank",
        config=_cfg(rerank_candidates=20),
    )
    assert seen["n"] == 20  # fused list sliced to rerank_candidates, not handed over whole
```

`fake_search` is a fixture monkeypatching `football_ai.rag.retrieval.dense_search` / `lexical_search` / `assert_text_search_config`, so these tests are pure. `_cfg(**overrides)` builds a `RagConfig` from `load()` with fields replaced.

- [ ] **Step 2: Write the failing DB tests**

```python
pytestmark = pytest.mark.db


def test_empty_corpus_raises_rather_than_abstaining(etl_conn, embedder):
    # zero results from an empty table is indistinguishable from a correct
    # abstention and would be read as "the corpus doesn't cover this"
    with etl_conn.transaction() as tx:
        etl_conn.execute("truncate football.kb_chunks")
        with pytest.raises(EmptyCorpusError, match="ingest-kb"):
            methodology_search(etl_conn, "yüzdelik", embed_fn=embedder.embed, mode="dense")
        tx.rollback()


def test_in_corpus_question_returns_cited_passages(ro_conn, embedder, reranker):
    result = methodology_search(
        ro_conn,
        "Yüzdelikler nasıl hesaplanıyor?",
        embed_fn=embedder.embed,
        rerank_fn=reranker.score,
    )
    assert not result.abstained
    assert any(p.topic == "percentile_methodology" for p in result.passages)
    assert all(p.source and p.title and p.content for p in result.passages)


def test_out_of_corpus_question_abstains(ro_conn, embedder, reranker):
    result = methodology_search(
        ro_conn, "Mbappé'nin maaşı ne kadar?", embed_fn=embedder.embed, rerank_fn=reranker.score
    )
    assert result.abstained and result.passages == []


def test_stale_text_search_config_is_refused(ro_conn, embedder):
    with pytest.raises(TextSearchConfigMismatchError):
        methodology_search(
            ro_conn,
            "yüzdelik",
            embed_fn=embedder.embed,
            mode="hybrid",
            config=_cfg(text_search_config="turkish"),
        )
```

The last two depend on the thresholds Task 8 measures; until then they are expected to fail and are the reason Task 8 exists. Note that in the task-8 commit if the numbers move.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_rag_retrieval.py -v`
Expected: FAIL, `ModuleNotFoundError: football_ai.rag.retrieval`

- [ ] **Step 4: Implement `methodology_search`**

Order of operations, because each early return skips real cost: validate `mode` against `VALID_MODES` and `rerank_fn` presence (`ValueError`); abstain immediately on a blank query, before embedding or connecting; call `assert_text_search_config` only for the two modes that use the lexical retriever; embed once with `embed_fn([query])[0]`; `dense_search` always; `lexical_search` for hybrid modes; `fuse` for hybrid modes; in `dense` mode synthesize the candidate list straight from the dense hits so the three modes share one downstream path; slice the candidate list to `rerank_candidates` before calling `rerank_fn`, because fusion can surface up to `dense_candidates + lexical_candidates` rows and the cross-encoder is the one stage whose cost scales with that number.

Mode → relevance signal, per the design doc's "RRF scores cannot support abstention" section. **The signal is computed over the full candidate list, not over the `top_n` that gets returned:**
- `dense`, `hybrid` → `dense_similarity`, the maximum over **all** `dense_candidates` dense hits (`None` when the dense list is empty), checked against `dense_abstain_threshold`.
- `hybrid_rerank` → `rerank_score`, the maximum over **all** `rerank_candidates` scored candidates, checked against `rerank_abstain_threshold`.

Why the full list rather than the returned five: "does the corpus cover this question" is a property of the query against the corpus, not of which rows ranking happened to select. Scoring the returned `top_n` instead couples abstention to the mode — fusion can push the strongest dense hit out of the top five (a chunk ranked 1st by dense and absent from the lexical list scores `1/(k+1)`, and two chunks ranked 3rd and 4th in *both* lists outrank it), so the signal becomes the second-best dense similarity and `hybrid` abstains on a question `dense` answers. Day 11's ablation would then report ranking quality and abstention coupling as one number.

An RRF score must never be used for this either: it is a function of ranks only, so the top hit of a nonsense query scores the same `1/(k+1) + 1/(k+1)` as a perfect match.

When below threshold, return `passages=[]`, `abstained=True`, `abstain_reason` starting with `ABSTAIN_MESSAGE` and naming the signal, score and threshold — a reason that reports the number is what makes Task 8's calibration auditable afterwards.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_rag_retrieval.py -v && uv run pytest tests/test_rag_retrieval_db.py -v -m db`
Expected: unit PASS; the two threshold-dependent DB tests may fail until Task 8 — record which.

- [ ] **Step 6: Commit**

```bash
git add src/football_ai/rag/retrieval.py tests/test_rag_retrieval.py tests/test_rag_retrieval_db.py
git commit -m "feat(rag): add methodology_search with modes and abstention"
```

---

### Task 7: `make kb-search`

**Files:**
- Create: `scripts/kb_search.py`
- Modify: `Makefile:17-20` (`.PHONY`), after `Makefile:105-106` (`ingest-kb`)
- Modify: `README.md` (command table)

**Interfaces:**
- Consumes: `methodology_search` (Task 6), `Embedder` (Day 9), `Reranker` (Task 5).

- [ ] **Step 1: Write `scripts/kb_search.py`**

`argparse` with `query` positional (joined from `$(Q)`), `--mode` defaulting to `hybrid_rerank`, `--top-n`. Calls `force_utf8()` first, connects with `readonly_dsn()` (the role the agent will use — if retrieval needs more than `SELECT`, that is a bug to find here and not on Day 13), constructs `Reranker().score` only for the reranking mode so the other two modes need no 600 MB download, prints per passage: rank, score(s), `title` — `source`, `topic`, and the first ~200 characters of `content`; prints the abstain reason and exits 0 when abstaining, because abstaining is a correct outcome rather than a failure.

- [ ] **Step 2: Add the Makefile target**

```make
kb-search:
	$(UV) run python scripts/kb_search.py $(Q) --mode $(MODE)
```

with `MODE ?= hybrid_rerank` near the other defaults, and `kb-search` added to `.PHONY`.

- [ ] **Step 3: Run it for each mode**

Run:
```bash
make kb-search Q="Yüzdelikler nasıl hesaplanıyor?" MODE=dense
make kb-search Q="player_season_club nedir?" MODE=hybrid
make kb-search Q="Yüzdelikler nasıl hesaplanıyor?" MODE=hybrid_rerank
make kb-search Q="Mbappé'nin maaşı ne kadar?"
```
Expected: the first three print cited passages, the last abstains. Keep the output — Task 8 needs the second query as its fusion evidence.

- [ ] **Step 4: Add `make kb-search` to the README command table**

- [ ] **Step 5: Commit**

```bash
git add scripts/kb_search.py Makefile README.md
git commit -m "feat(rag): add make kb-search for hand-run retrieval"
```

---

### Task 8: Calibrate the thresholds and record the measurement

**Files:**
- Create: `evals/rag/abstain_calibration.yaml`
- Create: `scripts/calibrate_abstain.py`
- Modify: `config/rag.yaml` (the two thresholds)
- Modify: `DECISIONS.md` (append `D-035`), `CLAUDE.md` (new day-10 section + status line), `docs/PLAN.md` (day-10 status note)
- Test: `tests/test_rag_retrieval_db.py` (the two threshold-dependent tests from Task 6 must now pass)

**Interfaces:**
- Consumes: `methodology_search` (Task 6).

- [ ] **Step 1: Write `evals/rag/abstain_calibration.yaml`**

Two lists, following `evals/sql/questions.yaml`'s posture (the data is the artefact, the script only reads it):

```yaml
version: 1
in_corpus:        # ~10, spread across the three kb/ groups
  - question: "Yüzdelikler nasıl hesaplanıyor?"
    expect_topic: percentile_methodology
  # ... metric categories, project methodology, data dictionary
out_of_corpus:    # ~10, deliberately uncovered
  - question: "Mbappé'nin maaşı ne kadar?"
    why: transfer and salary data is not in the corpus
  # ... injuries, 2026/27 fixtures, other sports, nonsense strings
```

Day 11's gold set extends this file rather than retyping the questions, and its trap-rejection set is exactly `out_of_corpus`.

- [ ] **Step 2: Write `scripts/calibrate_abstain.py`**

Reads that yaml. For each question and each of the three modes, prints the relevance signal and score, then per mode: the minimum in-corpus score, the maximum out-of-corpus score, the gap between them, and the midpoint. Also prints per-query wall-clock latency per mode. `expect_topic` is printed next to the in-corpus scores as a sanity column — it is not asserted here; that is Day 11's recall measurement.

A threshold is only defensible if that gap is positive; if the two distributions overlap, print the overlapping questions by name rather than a midpoint, because the honest output is "these cases are not separable", and inventing a cut that splits them would be the unmeasured threshold the spec names as an anti-goal.

- [ ] **Step 3: Run it**

Run: `uv run python scripts/calibrate_abstain.py`
Expected: three score distributions, with the chosen cut and gap per mode.

- [ ] **Step 4: Set the measured thresholds in `config/rag.yaml`**

Replace the two placeholders with the measured midpoints and replace the placeholder comment with the measured numbers (min in-corpus, max out-of-corpus, chosen cut) so the next reader sees the evidence next to the value.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q && uv run pytest -m db -q && make lint`
Expected: all green, including Task 6's two threshold-dependent DB tests. If an in-corpus question still abstains, that is a finding to report with its score — not a threshold to lower until the test passes.

- [ ] **Step 6: Write `D-035` in `DECISIONS.md`**

Sections per the project convention (Bağlam, Karar, Değerlendirilen alternatifler, Sonuç/ölçüm, Tarih), covering: retrieve-don't-synthesize; `simple` text search config and why the dictionary choice is a migration; RRF over score normalization; why RRF cannot carry abstention and what each mode uses instead; the cross-encoder's placement and cost. `Sonuç/ölçüm` carries the four measurements the spec assigns to this day: the two threshold distributions with their gaps, abstention counts per mode on the out-of-corpus set, the hand-read fusion comparison from Task 7 step 3, and per-mode latency.

- [ ] **Step 7: Update `CLAUDE.md` and `docs/PLAN.md`**

A `## Retrieval (Gün 10)` section in the same voice as the existing day sections — the traps worth carrying forward, not a summary: RRF carries no absolute relevance; the text search config lives in the schema, not the config file; a cosine search cannot abstain on its own; the reranker reads question and passage together, which is why it goes last over 20 candidates. Tick day 10 in `## Durum` with the measured numbers, and add the day-10 status note to `docs/PLAN.md`.

- [ ] **Step 8: Commit**

```bash
git add evals/rag/abstain_calibration.yaml scripts/calibrate_abstain.py config/rag.yaml \
        DECISIONS.md CLAUDE.md docs/PLAN.md tests/test_rag_retrieval_db.py
git commit -m "feat(rag): calibrate abstention thresholds, record D-035"
```

---

## GSTACK REVIEW REPORT

| Runs | Status | Findings |
| --- | --- | --- |
| `/plan-eng-review` (claude, 2026-11-26) | complete | 5 raised, 2 accepted, 2 declined by user, 1 suppressed (<7 confidence) |

**Scope (Step 0).** 14 files + 7 test files, 6 new classes — over the 8-file/2-class complexity threshold. Judged not scope creep: `src/football_ai/scouting/` already uses the same one-concern-per-module layout (`calc.py`, `categories.py`, `descriptors.py`, `profile.py`, `similarity.py`). No scope reduction recommended beyond F2.

**Findings.**

| ID | Sev | Conf | Finding | Outcome |
| --- | --- | --- | --- | --- |
| F1 | P1 | 9/10 | Task 6: relevance signal taken over the returned `top_n` couples abstention to the mode. Fusion can displace the strongest dense hit out of the top five (dense-only hit scores `1/(k+1)`; two chunks ranked 3rd+4th in both lists outrank it), so `hybrid` abstains on a question `dense` answers, and Day 11's ablation reports ranking quality and abstention coupling as one number. | **Fixed** — signal now computed over all `dense_candidates` / all `rerank_candidates`. Regression test `test_dense_and_hybrid_agree_on_abstention_for_the_same_query` added to Task 6. |
| F2 | P2 | 8/10 | Task 8 hardcoded 20 calibration questions in `scripts/calibrate_abstain.py`; `evals/sql/questions.yaml` is the established pattern and Day 11 builds a 50-question gold set with a trap set. | **Fixed** — moved to `evals/rag/abstain_calibration.yaml`; Day 11 extends the data, and its trap set is the `out_of_corpus` list. |
| F3 | P2 | 7/10 | `assert_text_search_config` runs per query: one catalog roundtrip on the Day 13 agent's hot path for a process-level invariant. Proposed memoization plus a test proving it is actually called in hybrid modes. | **Declined by user** — stays per-call as planned. |
| F4 | P2 | 9/10 | No step re-runs `make ingest-kb` after migration 009 or asserts `content_tsv is not null` across all 50 rows. Verified the insert path survives the new generated column (`src/football_ai/rag/ingest.py:85` names its columns explicitly), so this is a verification gap, not a break. | **Declined by user** — no verification step added. |
| F5 | P3 | 6/10 | `Passage` duplicates six fields of `Hit`. | Suppressed from the main report (confidence < 7); recommendation was to keep as-is — `SimilarPlayer` draws the same internal-dataclass / API-boundary line. |

**Tests.** ~37 tests across 7 files, covering all four scored dimensions plus the five Review Focus input classes. One residual gap, accepted by the user under F3: nothing proves `assert_text_search_config` is actually invoked in the hybrid modes, so if the call is omitted the mismatch guard becomes silent dead code.

**Performance.** `bge-reranker-v2-m3` is XLM-R-large sized (~568M params); 20 pairs on CPU is plausibly 5–15 s per query, unmeasured. Task 8 measures per-mode latency. If it exceeds ~10 s/query, the lever is `rerank_candidates: 20 → 10`, not a different model — the model choice is what Day 11's ablation is testing.

**VERDICT: APPROVED WITH FIXES APPLIED.** F1 and F2 are in the plan. F3 and F4 were raised, declined, and are recorded here as accepted risk rather than silently dropped.

NO UNRESOLVED DECISIONS
