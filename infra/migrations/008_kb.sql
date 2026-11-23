-- 008_kb.sql
--
-- Day 9: RAG knowledge base chunks in pgvector. See
-- docs/superpowers/specs/2026-11-23-day9-rag-corpus-design.md.
--
-- Same posture as 005_similarity.sql's player_vectors: a table, not a view,
-- because chunking + embedding is a batch computation over kb/*.md, rebuilt
-- wholesale by scripts/ingest_kb.py (TRUNCATE + insert in one transaction).
--
-- topic is a fixed check constraint, mirroring player_vectors_weighting_check:
-- the 22 values below are the kb/ corpus's topic list (day 9 design, group
-- A/B/C). Adding a note with an existing topic needs no migration; adding a
-- new topic does - that friction is deliberate, so the corpus's shape is
-- visible in the schema, not just in a filename convention.
--
-- (doc_id, content_hash) is the duplicate-detection key: two chunks from the
-- same file hashing identically are an accidental re-ingest of the same
-- content, not two distinct facts.

create table football.kb_chunks (
    id            bigint generated always as identity primary key,
    doc_id        text not null,
    chunk_index   integer not null,
    topic         text not null,
    source        text not null,
    title         text not null,
    content       text not null,
    content_hash  text not null,
    embedding     vector(1024) not null,
    built_at      timestamptz not null,
    unique (doc_id, content_hash),
    constraint kb_chunks_topic_check
        check (topic in (
            'shooting', 'creation', 'passing', 'progression', 'defending',
            'duels', 'discipline', 'goalkeeping',
            'per90_normalization', 'minutes_threshold',
            'percentile_methodology', 'possession_adjustment',
            'position_groups', 'similarity_meaning', 'zscore_cosine',
            'xg_regression', 'sample_warnings',
            'openplay_data_model', 'season_vs_club', 'possession_proxy',
            'data_quality_policy', 'metric_glossary'
        ))
);

comment on table football.kb_chunks is
    'RAG corpus chunks, one row per markdown chunk under kb/. Built by '
    'scripts/ingest_kb.py from heading-based splits of kb/*.md. Retrieval '
    '(hybrid search, RRF, reranking) is day 10 - this table only stores the '
    'dense bge-m3 embedding.';

create index on football.kb_chunks (topic);

grant select on football.kb_chunks to football_ro;
