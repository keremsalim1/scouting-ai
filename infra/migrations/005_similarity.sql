-- 005_similarity.sql
--
-- Day 8: similarity vectors in pgvector. See DECISIONS.md D-032 and
-- docs/superpowers/specs/2026-11-19-day8-similarity-design.md.
--
-- A table, not a view: z-scores and PCA need a fitted population, which is a
-- batch computation rather than a per-row expression. scripts/build_vectors.py
-- rebuilds it in one transaction (TRUNCATE + insert), the same idempotency
-- posture as the day 2 ETL.
--
-- One vector space per BROAD position group (GK/DEF/MID/ATT), not per fine
-- group. Fine-group spaces would make the day's acceptance metric undefined:
-- a CB vector and an FB vector would carry different metrics in different
-- slots, so no cosine exists between them, and z-scoring inside the fine
-- group centres every group on zero, erasing the very CB-vs-FB signal the
-- metric measures.

create table football.player_vectors (
    comp                  text not null,
    season                text not null,
    player_id             integer not null references football.players,
    -- Fine group: what production search filters on.
    position_group        text not null,
    -- Broad group: which vector space this row lives in, i.e. the population
    -- its z-scores were taken against.
    position_group_broad  text not null,
    weighting             text not null,
    -- Fixed width because pgvector declares one dimension count per column,
    -- while broad groups need 11 (GK) to 35 (MID, every metric except
    -- discipline and goalkeeping). Every comparison happens inside one broad
    -- group, where all rows share the same padding, so the trailing zeros
    -- contribute identically to every pair and change no ranking.
    vec                   vector(35) not null,
    -- The real dimension count: len(metric_keys) for equal/role, the retained
    -- component count for pca.
    dims                  integer not null,
    -- Always the INPUT metrics, in order, including on pca rows - that is the
    -- provenance a scouting report has to be able to state. So for pca,
    -- cardinality(metric_keys) > dims.
    metric_keys           text[] not null,
    -- How many dimensions were imputed to the group mean because the player
    -- never attempted the action (day 4 emits no metric row at all) or because
    -- the possession adjustment could not be computed.
    imputed_dims          integer not null,
    built_at              timestamptz not null,
    primary key (comp, season, player_id, weighting),
    constraint player_vectors_weighting_check
        check (weighting in ('equal', 'role', 'pca'))
);

comment on table football.player_vectors is
    'Similarity vectors, one row per qualified player per weighting. Built by '
    'scripts/build_vectors.py from z-scored metric values within '
    '(comp, position_group_broad). Stale whenever config/metrics.yaml changes: '
    'similar_players() compares metric_keys against the live config and refuses '
    'rather than ranking against a stale feature set.';

-- Every search filters on both: the weighting the caller asked for, and the
-- broad group that defines the vector space.
create index on football.player_vectors (weighting, position_group_broad);
-- Production search narrows further to the fine group.
create index on football.player_vectors (weighting, position_group);

grant select on football.player_vectors to football_ro;
