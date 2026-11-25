# Day 10 — RAG retrieval: hybrid search, RRF, reranking, abstention: design

## Intent and why

Day 9 filled `football.kb_chunks` with 50 chunks and their bge-m3 dense
vectors, but nothing ever queried that table. Day 10 (`docs/PLAN.md` row
33) adds the retrieval layer on top of it and exposes it as
`methodology_search`, the tool Day 13's LangGraph agent will call when a
question is about *methodology* rather than about numbers.

The acceptance criteria are "every answer carries a citation" and "no
fabrication on out-of-corpus questions". The second one is the hard half,
and it is not an LLM-prompting problem: a vector search *always* returns
its nearest neighbours, because "nothing here is close" is not an answer
ANN search can give. Ask it about Mbappé's salary and it will happily
hand back five passages about possession adjustment. Fabrication starts
there — the agent receives irrelevant-but-plausible text and builds a
sentence out of it. So abstention has to happen in the retrieval layer,
below the LLM, by measuring relevance and returning nothing when it is
too low.

## Goals

- **Dense search** over `kb_chunks.embedding` with pgvector cosine
  distance (`<=>`), query embedded with the same bge-m3 model Day 9 used
  for the documents.
- **Full-text search** over chunk text using Postgres `tsvector` /
  `websearch_to_tsquery` / `ts_rank`, new migration `009_kb_fts.sql`:
  a stored generated `tsvector` column plus a GIN index. Reason it
  exists at all: exact technical terms (`npxg_per_shot`,
  `player_season_club`, "900 dakika") are where dense embeddings are
  weakest — to bge-m3, `npxG`, `xG` and `xA` are near-identical — and
  where lexical matching is strongest. The two retrievers fail on
  different questions, which is the only reason fusing them helps.
- **Text search configuration is `simple`** (no stemming, case folding
  only), decided with the user. The corpus is mixed-language: Turkish
  prose with English identifiers (`higher_is_better`, `comparison_scope`)
  in the same sentence. A Turkish snowball stemmer would mangle the
  identifiers; an English one would mangle the prose. `simple` is the
  option that is merely unhelpful rather than actively wrong on half the
  text. Day 11 is where this gets measured rather than reasoned about —
  but changing it is a migration, not a config edit (see "The text
  search configuration is baked into the schema" below).
- **RRF fusion** of the two ranked lists: `score = Σ 1/(k + rank)`,
  `k = 60`. The scores of the two retrievers are not comparable —
  cosine distance is bounded in [0, 2], `ts_rank` is unbounded and
  length-dependent — and normalizing them into a shared scale is
  fragile guesswork. Ranks are comparable without any assumption. Same
  principle Day 6 landed on for the SQL judge: when magnitudes cannot be
  compared, compare order.
- **Reranking** with `bge-reranker-v2-m3` (cross-encoder, run locally via
  `sentence-transformers`, same lazy-import posture as Day 9's
  `Embedder`). RRF's top 20 candidates go in, top 5 come out. A
  cross-encoder reads question and passage *together*, so it can judge
  relevance that a bi-encoder cannot: the document embeddings were
  computed before the question existed. Cost: ~600 MB download and
  seconds of CPU per query, which is why it is the last stage over 20
  candidates and not a scorer over all 50 chunks.
- **Abstention**, measured rather than guessed: if the best candidate's
  relevance score is below a threshold, return zero results with an
  explicit "not in the knowledge base" reason instead of the nearest
  irrelevant passage.
- **`methodology_search(conn, query, ...)`** returning a Pydantic model,
  with `source` and `title` present on every passage (both are `not null`
  in `kb_chunks`, so citation is a schema guarantee, not a convention).
- **Three independently runnable modes** — `dense`, `hybrid`,
  `hybrid_rerank` — because Day 11's ablation compares exactly these
  three and a mode that can only run as part of the full pipeline cannot
  be ablated.
- **`make kb-search Q="..."`** to run a query by hand and read the
  output. This is a way to look at the thing, not a measurement; Day 11
  owns measurement.

## Non-goals

- **Writing an answer.** Decided with the user: `methodology_search`
  retrieves and cites, it does not synthesize. Composing prose from the
  passages belongs to the agent (Day 13), for three reasons: the project
  rule is that the LLM interprets what a tool produced rather than
  producing it; a second LLM layer inside the tool would summarize a
  summary and compound its errors; and a tool that returns passages can
  be scored for recall@5 for free, while a tool that returns a paragraph
  needs a judge — and Day 6 showed that a flawed judge costs more
  accuracy than a flawed model.
- Retrieval evaluation: the 50-question gold set, recall@5, faithfulness,
  trap-rejection rate, MLflow, and the dense/hybrid/+reranker ablation
  are all Day 11.
- Tuning the retrieval parameters (`k`, candidate depth, text search
  config, thresholds). Day 10 picks defaults and makes them
  configurable; Day 11 measures them.
- bge-m3 sparse / multi-vector output. Postgres full-text is the lexical
  retriever; a second embedding pass to produce learned sparse vectors
  is not needed to satisfy "hybrid" and would add a storage format and a
  model call for no measured gain.
- Any LLM call anywhere in this layer. Retrieval is deterministic and
  free; the only models involved run locally.
- Query rewriting, HyDE, multi-query expansion, conversational
  follow-ups.

## Anti-goals — what would make this a failure even if it ran

- **Returning something for every question.** A retrieval layer that
  never abstains has not solved the acceptance criterion, it has moved
  the fabrication one layer up where it is harder to see.
- **Abstaining on real questions.** The mirror failure, and the more
  likely one once a threshold exists. A threshold tight enough to reject
  "Mbappé'nin maaşı" but loose enough to accept a badly worded question
  about percentiles is the whole point; a threshold that rejects both is
  not safety, it is a broken tool.
- **An unmeasured threshold.** Picking a number because it looks round
  is exactly the move this project keeps refusing. The number comes from
  looking at the score distributions of in-corpus and out-of-corpus
  questions and choosing where they separate — and the measurement gets
  written down.
- **Hybrid search that is dense search with extra steps.** If full-text
  contributes nothing to the fused ranking, then the migration, the
  index and the fusion code are cost without benefit. Day 11 has to be
  able to see this, which means the modes must be separable.

## Constraints

- Student budget (~$5 total LLM spend). Nothing here may call a paid API.
  Both models run locally on CPU.
- CI runs no LLM, no ETL, no model download (Day 6 rule, applied to RAG
  in D-034). Unit tests inject fake embed/rerank callables; DB tests use
  synthetic vectors, as Day 9's do. The real models are exercised only
  by `make ingest-kb` / `make kb-search` on the developer's machine.
- `football_ro` must be able to run everything in this layer. Retrieval
  is read-only; the Day 13 agent sees only that role.
- Windows: any script that prints must call
  `football_ai.console.force_utf8()`.
- 50 chunks is a small corpus. Latency targets are not interesting here;
  correctness and abstention are. The reranker's per-query seconds are
  acceptable at this size and are a known scaling limit, not a bug.

## The parts that are decided

### Pipeline shape

```
query
  ├─ dense:     embed(query) → ORDER BY embedding <=> q LIMIT 20   → ranked list A
  └─ lexical:   websearch_to_tsquery('simple', query) → ts_rank LIMIT 20 → ranked list B
                         │
                    RRF(A, B, k=60) → top 20
                         │
              rerank(query, candidates) → top 5
                         │
              abstention check on the top result
                         │
              MethodologySearchResult
```

Mode selection truncates this pipeline: `dense` stops after list A,
`hybrid` stops after RRF, `hybrid_rerank` runs all of it.

### Where abstention gets its signal — the one structural subtlety

**RRF scores cannot support abstention, by construction.** An RRF score
is a function of ranks only, so the top result of a totally irrelevant
query gets the same `1/(60+1) + 1/(60+1)` as the top result of a perfect
match. The fused score says "this was ranked highly by both retrievers",
not "this is relevant". So each mode needs its own absolute relevance
signal:

- `dense` — cosine similarity of the top hit (`1 - distance`).
- `hybrid` — also the cosine similarity of the top fused hit, looked up
  from the dense scores, falling back to "no dense score for this
  candidate" (a lexical-only hit) meaning it cannot clear the threshold
  on its own.
- `hybrid_rerank` — the cross-encoder score, which is the only one of
  the three that is an actual relevance judgment.

Two thresholds therefore exist (a cosine one and a reranker one), both
measured, both configurable, and the report says which one fired.

### Configuration

Retrieval parameters live in `config/rag.yaml`, following the
`config/metrics.yaml` precedent from Day 4 (runtime authority, not
documentation): `rrf_k`, candidate depths, `top_n`, text search
configuration name, and the two abstention thresholds. Changing a
threshold must not require a migration or a code edit, because Day 11
will change them repeatedly while measuring.

### The text search configuration is baked into the schema

A stored generated column requires an immutable expression, so
`to_tsvector('simple', …)` hardcodes `simple` in `009_kb_fts.sql`. That
sits awkwardly next to the config file, and the resolution is explicit:
`config/rag.yaml` carries the configuration name so the *query side*
uses the same one as the index, and the retrieval code fails loudly if
the two disagree rather than silently running an unindexed or
differently-stemmed search. Switching to a Turkish or English dictionary
in Day 11 means a new migration (`010_…`). That friction is the same
deliberate kind as D-034's topic check constraint: what the index
actually contains stays visible in the schema.

### Builder's calls, settled here rather than left open

- **Empty `tsquery`.** A query of only punctuation or stopwords yields an
  empty query and an empty lexical list. RRF then degrades to dense-only
  ranking; this is not an error and is not reported as one. (Under
  `simple` there is no stopword list, so this is rare — but the code may
  not assume both lists are non-empty.)
- **Reranker score scale.** `bge-reranker-v2-m3` emits unbounded logits.
  The layer applies a sigmoid so the stored and thresholded score is in
  [0, 1] and a threshold in `config/rag.yaml` is a readable number.
- **`top_n` applies to every mode**, including `dense`, so the three
  ablation modes return comparably sized result sets.
- **No `topic` filter parameter.** The agent could in principle restrict
  retrieval to one of the 22 topics, but nothing in Day 10 or Day 11
  needs it and it would be a second, untested retrieval path.
- **`make kb-search` takes the mode as a variable** (`MODE=`), defaulting
  to `hybrid_rerank`, so all three are reachable by hand.

### Return shape

A Pydantic `MethodologySearchResult`: the query, the mode, the retrieved
passages, `abstained: bool`, and a human-readable `abstain_reason` when
it did. Each passage carries `doc_id`, `chunk_index`, `topic`, `source`,
`title`, `content`, and whichever scores its mode produced (dense rank
and similarity, lexical rank and `ts_rank`, RRF score, reranker score) —
provenance, in the same spirit as Day 8's `metric_keys`: a consumer must
be able to say *why* a passage was returned.

### Measurement this day owns

Day 11 owns quality metrics. Day 10 must still report numbers, and these
are its own:

1. The score distributions behind the two thresholds: a handful of
   in-corpus questions and a handful of deliberately out-of-corpus ones,
   with the chosen cut and the gap at that cut.
2. Abstention behaviour on those out-of-corpus questions: how many
   returned zero results, in each of the three modes.
3. One hand-read comparison where dense and lexical disagree, showing
   what fusion changed — the cheapest available evidence that full-text
   is not dead weight.
4. Per-query latency per mode, so the reranker's cost is a number rather
   than an adjective.

## What is left to the builder

- Module layout under `src/football_ai/rag/` (search / fusion / rerank /
  the tool entry point), and how `conn` and the model callables are
  injected so tests can fake them — Day 9's `embed_fn` parameter is the
  pattern to follow.
- Whether the `tsvector` lives in a stored generated column or an
  expression index, and exactly which fields are concatenated into it
  (title and content, with whatever weighting is defensible).
- Default values for `rrf_k`, candidate depth and `top_n`; the ones in
  the pipeline sketch above are the starting point, not a requirement.
- Which specific questions make up the threshold-calibration set, and
  how that evidence is recorded (a short section in the decision entry
  is enough; this is not Day 11's gold set).
- Test boundaries: which behaviour is a pure unit test with fake models
  and which needs a live `kb_chunks`.
- The `D-035` decision entry in `DECISIONS.md` and the `CLAUDE.md`
  status/section update.
