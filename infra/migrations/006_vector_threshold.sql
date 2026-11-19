-- 006_vector_threshold.sql
--
-- Day 8 follow-up: record which minimum-minutes threshold a vector was fitted
-- under, so similar_players() can refuse a stale one.
--
-- 005's staleness check compared metric_keys only, which catches a metric
-- being added or removed but not a threshold change. min_minutes decides who
-- is in the population, so changing it changes every z-score, every column
-- mean and the whole PCA basis - while leaving the key list byte-identical.
-- config/metrics.yaml is runtime authority (day 4: "eşik değiştirmek migration
-- gerektirmez"), which is exactly what makes the silent version of this
-- possible.
--
-- Nullable on purpose: rows built before this column existed cannot say what
-- threshold produced them, and "unknown" must read as stale rather than as
-- agreement. The next `make build-vectors` fills it in.

alter table football.player_vectors
    add column if not exists min_minutes integer;

comment on column football.player_vectors.min_minutes is
    'The config/metrics.yaml min_minutes this vector was fitted under. '
    'similar_players() raises StaleVectorsError when it differs from the live '
    'config, or is NULL (built before this column existed).';
