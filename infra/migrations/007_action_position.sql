-- 007_action_position.sql
--
-- Day 8 follow-up: where a player operates, as two similarity dimensions.
--
-- The first measurement put position consistency at 68.9% against a 90% target,
-- and the midfield carried the shortfall (DM 41.5%, CM 54.0%, AM 58.5%). The
-- label-noise hypothesis was tested and refuted: restricting to
-- position_share >= 0.8 moved the headline only to 70.5%, and DM fell. What was
-- actually missing is spatial information - all 38 metrics in metrics.yaml are
-- volume or rate measures, while a DM, a CM and an AM differ mainly in where
-- they play. Measured on pass origin:
--
--   DM x=50.6 (sd 3.2)   CM x=53.2 (sd 4.1)   AM x=60.5 (sd 3.5)
--   FW |y-50|=24.6 (sd 4.5)                   W  |y-50|=32.1 (sd 3.2)
--
-- Both separations are ~1.9 sd, stronger than anything already in the vector.
--
-- These are NOT metrics and deliberately do not enter config/metrics.yaml: that
-- file requires higher_is_better on every entry, and playing deep is not better
-- or worse than playing high. See src/football_ai/scouting/descriptors.py.
--
-- Passes are the source rather than shots or touches: Day 1 confirmed pass
-- coordinates are 100% populated, and passes are by far the highest-volume
-- on-ball event, so the mean is stable even for low-minute qualifiers.

create or replace view football.player_action_position as
select
    comp,
    season,
    player_id,
    avg(x)::double precision            as action_x,
    -- Distance from the centre line, not raw y: a left-back and a right-back
    -- are the same role mirrored, so raw y would place them at opposite
    -- extremes and call them dissimilar.
    avg(abs(y - 50))::double precision  as action_lateral_dev,
    count(*)                            as n_passes
from football.passes
where x is not null and y is not null
group by comp, season, player_id;

comment on view football.player_action_position is
    'Mean pass-origin depth and distance from the centre line, per player per '
    'league-season. Role descriptors for the day 8 similarity vector - not '
    'performance metrics: a pitch coordinate has no direction of merit, which '
    'is why they are not in config/metrics.yaml.';

grant select on football.player_action_position to football_ro;

-- The vector gains two dimensions, so the widest broad group (MID) goes from
-- 35 to 37. pgvector declares one dimension count per column and cannot widen
-- existing values, so the rows are discarded and rebuilt - safe because
-- player_vectors is a derived batch artefact and `make build-vectors`
-- regenerates it in full. Until it is run, similar_players() raises
-- StaleVectorsError rather than ranking against a half-built table.
truncate football.player_vectors;

alter table football.player_vectors
    alter column vec type vector(37);
