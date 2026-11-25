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
--
-- Title weighted A, body B: a heading match outranks an incidental body
-- mention of the same term, which is the ranking a reader expects when a kb/
-- note is *about* the thing they asked for.

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
