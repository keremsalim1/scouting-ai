-- 002_position_and_season_views.sql
--
-- Day 3: give every player one position group, and expose season totals and
-- per-90 rates as views. See DECISIONS.md D-014..D-016.
--
-- Views rather than tables: these are pure functions of the fact tables, so
-- materialising them would add a refresh step that can go stale. 35k rows
-- aggregate in milliseconds. Revisit only if a measurement says to.

-- ===========================================================================
-- Position grouping
--
-- Eight groups, chosen by measuring how many players land in each one rather
-- than by taste. Two decisions came out of that measurement:
--
--  * DML/DMR are mapped to FB, not DM. They are the wing-back slot in a 3-5-2.
--    Serie A plays DML/DMR for 9.1% of minutes against 6.2% for DL/DR, England
--    the reverse (2.8% vs 13.7%). Grouping them as midfielders left Serie A
--    with 22 full-backs; as wing-backs the three leagues read 65/69/67, which
--    is what you expect when every team fields two wide defenders.
--  * ML/MR join the wingers rather than forming their own group. On their own
--    they gave 5/22/0 players per league at 900+ minutes - no basis for a
--    percentile.
--
-- Even so, Serie A is thin at DM (10), W (10) and AM (14). That is why the
-- broad group exists: day 4 falls back to it when the fine group is too small
-- to support a percentile.
-- ===========================================================================

create or replace function football.position_group(position_code text)
returns text language sql immutable parallel safe as $$
    select case position_code
        when 'GK'  then 'GK'
        when 'DC'  then 'CB'
        when 'DL'  then 'FB'
        when 'DR'  then 'FB'
        when 'DML' then 'FB'   -- wing-back
        when 'DMR' then 'FB'   -- wing-back
        when 'DMC' then 'DM'
        when 'MC'  then 'CM'
        when 'AMC' then 'AM'
        when 'ML'  then 'W'
        when 'MR'  then 'W'
        when 'AML' then 'W'
        when 'AMR' then 'W'
        when 'FW'  then 'FW'
        when 'FWL' then 'FW'
        when 'FWR' then 'FW'
    end
$$;

comment on function football.position_group(text) is
    'Maps a raw OpenPlay position code to one of GK, CB, FB, DM, CM, AM, W, FW. '
    'Returns NULL for Sub and for unknown codes.';

create or replace function football.position_group_broad(group_code text)
returns text language sql immutable parallel safe as $$
    select case group_code
        when 'GK' then 'GK'
        when 'CB' then 'DEF'
        when 'FB' then 'DEF'
        when 'DM' then 'MID'
        when 'CM' then 'MID'
        when 'AM' then 'MID'
        when 'W'  then 'ATT'
        when 'FW' then 'ATT'
    end
$$;

comment on function football.position_group_broad(text) is
    'Collapses the eight position groups into GK/DEF/MID/ATT, used as the '
    'comparison pool when a fine group has too few players for a percentile.';


-- ===========================================================================
-- position_map: one row per player per league-season.
--
-- Primary rule: the minute-weighted most frequent *starting* position.
-- `position` in the source is the starting position and reads 'Sub' for
-- players who came off the bench, so substitute minutes carry no positional
-- information and are excluded from the vote (D-005).
--
-- `position_source` records which rule produced the answer, because the
-- answer is not equally trustworthy for everyone:
--   starts        - voted from real starting minutes (the overwhelming majority)
--   main_position - never started; fell back to the players dimension
--   unknown       - never started and no main_position either
--
-- A third option was measured and rejected: classifying by median pass
-- position. Nearest-centroid on players with 50+ passes scored 70.9% overall
-- but only 32% for AM and 37% for CM, and the players who actually need the
-- fallback average 13 passes. Saying "unknown" beats guessing. None of the
-- unknown players reaches 900 minutes, so no percentile population is
-- affected.
--
-- `position_share` is the dominant position's share of starting minutes. It
-- is below 0.6 for roughly one player in six, which is genuine positional
-- ambiguity that a scouting report should surface rather than hide.
-- ===========================================================================

create or replace view football.position_map as
with start_minutes as (
    select
        comp, season, player_id, position,
        football.position_group(position) as grp,
        sum(minutes_played)::bigint       as minutes
    from football.player_match_stats
    where position <> 'Sub'
    group by 1, 2, 3, 4, 5
),
-- The vote happens at GROUP level, not at raw-position level, because the
-- group is what the answer is used for. A player with DL 400 + DR 300 + AMC
-- 500 belongs in FB (700 minutes), even though AMC is their single biggest
-- slot. Voting per raw code would have put them in AM.
group_minutes as (
    select
        comp, season, player_id, grp,
        sum(minutes) as minutes,
        sum(sum(minutes)) over (partition by comp, season, player_id)
            as total_start_minutes,
        -- Ties broken by group code so the view is deterministic.
        row_number() over (
            partition by comp, season, player_id order by sum(minutes) desc, grp
        ) as rn
    from start_minutes
    group by 1, 2, 3, 4
),
dominant_group as (
    select comp, season, player_id, grp, minutes, total_start_minutes
    from group_minutes
    where rn = 1
),
-- Within the winning group, report the biggest raw slot, so a report can say
-- "DL" rather than only "FB".
dominant as (
    select distinct on (sm.comp, sm.season, sm.player_id)
        sm.comp, sm.season, sm.player_id, sm.position,
        dg.grp, dg.minutes, dg.total_start_minutes
    from start_minutes sm
    join dominant_group dg using (comp, season, player_id)
    where sm.grp = dg.grp
    order by sm.comp, sm.season, sm.player_id, sm.minutes desc, sm.position
),
every_player as (
    select distinct comp, season, player_id
    from football.player_match_stats
)
select
    e.comp,
    e.season,
    e.player_id,
    pl.player,
    coalesce(d.position, pl.main_position)                      as position,
    coalesce(
        d.grp,
        football.position_group(pl.main_position),
        'UNK'
    )                                                            as position_group,
    coalesce(
        football.position_group_broad(d.grp),
        football.position_group_broad(football.position_group(pl.main_position)),
        'UNK'
    )                                                            as position_group_broad,
    case
        when d.grp is not null            then 'starts'
        when pl.main_position is not null then 'main_position'
        else 'unknown'
    end                                                          as position_source,
    -- Share of the player's starting minutes spent in the winning group.
    -- Below 0.6 means the group label is a simplification worth flagging.
    (d.minutes::double precision / nullif(d.total_start_minutes, 0)) as position_share,
    coalesce(d.total_start_minutes, 0)                           as start_minutes
from every_player e
join football.players pl using (player_id)
left join dominant d using (comp, season, player_id);

comment on view football.position_map is
    'One position group per player per league-season, voted from minute-weighted '
    'starting positions. Check position_source and position_share before trusting it.';


-- ===========================================================================
-- player_season_club: season totals per player AND club.
--
-- This is the grain op.player_season_stats uses, so it is what the cross-check
-- compares against. A player who moved clubs mid-season has two rows here.
--
-- Counting stats keep integer arithmetic. xa/xg/npxg are `real` in the source,
-- so they are widened to double precision before summing: accumulating a
-- thousand float4 values loses precision that matters when the result is then
-- compared to 0.01 tolerance.
-- ===========================================================================

create or replace view football.player_season_club as
select
    s.comp,
    s.season,
    s.player_id,
    max(s.player)                                         as player,
    s.team_id,
    max(s.team)                                           as team,
    count(*)::bigint                                      as matches,
    count(*) filter (where s.is_starter)::bigint          as starts,
    sum(s.minutes_played)::bigint                         as minutes_played,
    sum(s.touches)::bigint                                as touches,
    sum(s.passes)::bigint                                 as passes,
    sum(s.passes_completed)::bigint                       as passes_completed,
    sum(s.passes_final_third)::bigint                     as passes_final_third,
    sum(s.passes_into_box)::bigint                        as passes_into_box,
    sum(s.progressive_passes)::bigint                     as progressive_passes,
    sum(s.crosses)::bigint                                as crosses,
    sum(s.crosses_completed)::bigint                      as crosses_completed,
    sum(s.long_balls)::bigint                             as long_balls,
    sum(s.long_balls_completed)::bigint                   as long_balls_completed,
    sum(s.through_balls)::bigint                          as through_balls,
    sum(s.through_balls_completed)::bigint                as through_balls_completed,
    sum(s.headed_passes)::bigint                          as headed_passes,
    sum(s.chipped_passes)::bigint                         as chipped_passes,
    sum(s.layoffs)::bigint                                as layoffs,
    sum(s.key_passes)::bigint                             as key_passes,
    sum(s.assists)::bigint                                as assists,
    sum(s.xa::double precision)                           as xa,
    sum(s.big_chances_created)::bigint                    as big_chances_created,
    sum(s.corners_taken)::bigint                          as corners_taken,
    sum(s.free_kicks_taken)::bigint                       as free_kicks_taken,
    sum(s.throw_ins)::bigint                              as throw_ins,
    sum(s.goal_kicks)::bigint                             as goal_kicks,
    sum(s.keeper_throws)::bigint                          as keeper_throws,
    sum(s.shots)::bigint                                  as shots,
    sum(s.shots_on_target)::bigint                        as shots_on_target,
    sum(s.shots_off_target)::bigint                       as shots_off_target,
    sum(s.shots_blocked)::bigint                          as shots_blocked,
    sum(s.shots_on_post)::bigint                          as shots_on_post,
    sum(s.shots_inside_box)::bigint                       as shots_inside_box,
    sum(s.shots_outside_box)::bigint                      as shots_outside_box,
    sum(s.headed_shots)::bigint                           as headed_shots,
    sum(s.goals)::bigint                                  as goals,
    sum(s.headed_goals)::bigint                           as headed_goals,
    sum(s.penalty_goals)::bigint                          as penalty_goals,
    sum(s.penalties_taken)::bigint                        as penalties_taken,
    sum(s.penalties_missed)::bigint                       as penalties_missed,
    sum(s.own_goals)::bigint                              as own_goals,
    sum(s.non_penalty_goals)::bigint                      as non_penalty_goals,
    sum(s.xg::double precision)                           as xg,
    sum(s.npxg::double precision)                         as npxg,
    sum(s.big_chances)::bigint                            as big_chances,
    sum(s.big_chances_missed)::bigint                     as big_chances_missed,
    sum(s.goals_disallowed)::bigint                       as goals_disallowed,
    sum(s.dribbles)::bigint                               as dribbles,
    sum(s.dribbles_completed)::bigint                     as dribbles_completed,
    sum(s.dribbled_past)::bigint                          as dribbled_past,
    sum(s.miscontrols)::bigint                            as miscontrols,
    sum(s.dispossessed)::bigint                           as dispossessed,
    sum(s.tackles)::bigint                                as tackles,
    sum(s.tackles_won)::bigint                            as tackles_won,
    sum(s.interceptions)::bigint                          as interceptions,
    sum(s.clearances)::bigint                             as clearances,
    sum(s.shot_blocks)::bigint                            as shot_blocks,
    sum(s.pass_blocks)::bigint                            as pass_blocks,
    sum(s.ball_recoveries)::bigint                        as ball_recoveries,
    sum(s.aerials)::bigint                                as aerials,
    sum(s.aerials_won)::bigint                            as aerials_won,
    sum(s.fouls_committed)::bigint                        as fouls_committed,
    sum(s.fouls_won)::bigint                              as fouls_won,
    sum(s.offsides)::bigint                               as offsides,
    sum(s.offsides_provoked)::bigint                      as offsides_provoked,
    sum(s.errors)::bigint                                 as errors,
    sum(s.errors_leading_to_shot)::bigint                 as errors_leading_to_shot,
    sum(s.errors_leading_to_goal)::bigint                 as errors_leading_to_goal,
    sum(s.saves)::bigint                                  as saves,
    sum(s.claims)::bigint                                 as claims,
    sum(s.claims_failed)::bigint                          as claims_failed,
    sum(s.punches)::bigint                                as punches,
    sum(s.keeper_sweeper)::bigint                         as keeper_sweeper,
    sum(s.smothers)::bigint                               as smothers,
    sum(s.keeper_pickups)::bigint                         as keeper_pickups,
    sum(s.yellow_cards)::bigint                           as yellow_cards,
    sum(s.second_yellows)::bigint                         as second_yellows,
    sum(s.red_cards)::bigint                              as red_cards
from football.player_match_stats s
group by s.comp, s.season, s.player_id, s.team_id;

comment on view football.player_season_club is
    'Season totals per player AND club. A mid-season transfer gives two rows. '
    'Use player_season unless you specifically want the club split.';


-- ===========================================================================
-- player_season: one row per player per league-season.
--
-- Deliberately a separate view rather than a `team_id IS NULL` row inside
-- player_season_club: mixing both grains in one relation makes
-- `SELECT ... FROM player_season` silently double-count the 48 players who
-- changed clubs. Two views cannot be misread that way.
-- ===========================================================================

create or replace view football.player_season as
select
    c.comp,
    c.season,
    c.player_id,
    max(c.player)                                         as player,
    count(*)::int                                         as clubs,
    string_agg(c.team, ' / ' order by c.minutes_played desc) as teams,
    pm.position,
    pm.position_group,
    pm.position_group_broad,
    pm.position_source,
    pm.position_share,
    sum(c.matches)                                        as matches,
    sum(c.starts)                                         as starts,
    sum(c.minutes_played)                                 as minutes_played,
    sum(c.touches)                                        as touches,
    sum(c.passes)                                         as passes,
    sum(c.passes_completed)                               as passes_completed,
    sum(c.passes_final_third)                             as passes_final_third,
    sum(c.passes_into_box)                                as passes_into_box,
    sum(c.progressive_passes)                             as progressive_passes,
    sum(c.crosses)                                        as crosses,
    sum(c.crosses_completed)                              as crosses_completed,
    sum(c.long_balls)                                     as long_balls,
    sum(c.long_balls_completed)                           as long_balls_completed,
    sum(c.through_balls)                                  as through_balls,
    sum(c.through_balls_completed)                        as through_balls_completed,
    sum(c.headed_passes)                                  as headed_passes,
    sum(c.chipped_passes)                                 as chipped_passes,
    sum(c.layoffs)                                        as layoffs,
    sum(c.key_passes)                                     as key_passes,
    sum(c.assists)                                        as assists,
    sum(c.xa)                                             as xa,
    sum(c.big_chances_created)                            as big_chances_created,
    sum(c.corners_taken)                                  as corners_taken,
    sum(c.free_kicks_taken)                               as free_kicks_taken,
    sum(c.throw_ins)                                      as throw_ins,
    sum(c.goal_kicks)                                     as goal_kicks,
    sum(c.keeper_throws)                                  as keeper_throws,
    sum(c.shots)                                          as shots,
    sum(c.shots_on_target)                                as shots_on_target,
    sum(c.shots_off_target)                               as shots_off_target,
    sum(c.shots_blocked)                                  as shots_blocked,
    sum(c.shots_on_post)                                  as shots_on_post,
    sum(c.shots_inside_box)                               as shots_inside_box,
    sum(c.shots_outside_box)                              as shots_outside_box,
    sum(c.headed_shots)                                   as headed_shots,
    sum(c.goals)                                          as goals,
    sum(c.headed_goals)                                   as headed_goals,
    sum(c.penalty_goals)                                  as penalty_goals,
    sum(c.penalties_taken)                                as penalties_taken,
    sum(c.penalties_missed)                               as penalties_missed,
    sum(c.own_goals)                                      as own_goals,
    sum(c.non_penalty_goals)                              as non_penalty_goals,
    sum(c.xg)                                             as xg,
    sum(c.npxg)                                           as npxg,
    sum(c.big_chances)                                    as big_chances,
    sum(c.big_chances_missed)                             as big_chances_missed,
    sum(c.goals_disallowed)                               as goals_disallowed,
    sum(c.dribbles)                                       as dribbles,
    sum(c.dribbles_completed)                             as dribbles_completed,
    sum(c.dribbled_past)                                  as dribbled_past,
    sum(c.miscontrols)                                    as miscontrols,
    sum(c.dispossessed)                                   as dispossessed,
    sum(c.tackles)                                        as tackles,
    sum(c.tackles_won)                                    as tackles_won,
    sum(c.interceptions)                                  as interceptions,
    sum(c.clearances)                                     as clearances,
    sum(c.shot_blocks)                                    as shot_blocks,
    sum(c.pass_blocks)                                    as pass_blocks,
    sum(c.ball_recoveries)                                as ball_recoveries,
    sum(c.aerials)                                        as aerials,
    sum(c.aerials_won)                                    as aerials_won,
    sum(c.fouls_committed)                                as fouls_committed,
    sum(c.fouls_won)                                      as fouls_won,
    sum(c.offsides)                                       as offsides,
    sum(c.offsides_provoked)                              as offsides_provoked,
    sum(c.errors)                                         as errors,
    sum(c.errors_leading_to_shot)                         as errors_leading_to_shot,
    sum(c.errors_leading_to_goal)                         as errors_leading_to_goal,
    sum(c.saves)                                          as saves,
    sum(c.claims)                                         as claims,
    sum(c.claims_failed)                                  as claims_failed,
    sum(c.punches)                                        as punches,
    sum(c.keeper_sweeper)                                 as keeper_sweeper,
    sum(c.smothers)                                       as smothers,
    sum(c.keeper_pickups)                                 as keeper_pickups,
    sum(c.yellow_cards)                                   as yellow_cards,
    sum(c.second_yellows)                                 as second_yellows,
    sum(c.red_cards)                                      as red_cards
from football.player_season_club c
join football.position_map pm using (comp, season, player_id)
group by
    c.comp, c.season, c.player_id,
    pm.position, pm.position_group, pm.position_group_broad,
    pm.position_source, pm.position_share;

comment on view football.player_season is
    'One row per player per league-season, clubs combined, with the position '
    'group attached. This is the grain scouting questions are asked at.';


-- ===========================================================================
-- player_per90: rates, built on player_season.
--
-- Two rules from D-004 are enforced here rather than left to the caller:
--   * per-90 divides by real (expanded) minutes, so a full match is ~98-101
--     minutes, not 90. Values sit 8-11% below nominal-90 sources.
--   * ratios are ratios of sums, never averages of per-match percentages.
--     nullif() makes a zero denominator produce NULL, not 0.
-- ===========================================================================

create or replace view football.player_per90 as
select
    comp,
    season,
    player_id,
    player,
    clubs,
    teams,
    position,
    position_group,
    position_group_broad,
    position_source,
    position_share,
    matches,
    starts,
    minutes_played,

    touches              / minutes_played::double precision * 90 as touches_per90,
    passes               / minutes_played::double precision * 90 as passes_per90,
    passes_completed     / minutes_played::double precision * 90 as passes_completed_per90,
    passes_final_third   / minutes_played::double precision * 90 as passes_final_third_per90,
    passes_into_box      / minutes_played::double precision * 90 as passes_into_box_per90,
    progressive_passes   / minutes_played::double precision * 90 as progressive_passes_per90,
    crosses              / minutes_played::double precision * 90 as crosses_per90,
    long_balls           / minutes_played::double precision * 90 as long_balls_per90,
    through_balls        / minutes_played::double precision * 90 as through_balls_per90,
    key_passes           / minutes_played::double precision * 90 as key_passes_per90,
    assists              / minutes_played::double precision * 90 as assists_per90,
    xa                   / minutes_played::double precision * 90 as xa_per90,
    big_chances_created  / minutes_played::double precision * 90 as big_chances_created_per90,
    shots                / minutes_played::double precision * 90 as shots_per90,
    shots_on_target      / minutes_played::double precision * 90 as shots_on_target_per90,
    goals                / minutes_played::double precision * 90 as goals_per90,
    non_penalty_goals    / minutes_played::double precision * 90 as non_penalty_goals_per90,
    xg                   / minutes_played::double precision * 90 as xg_per90,
    npxg                 / minutes_played::double precision * 90 as npxg_per90,
    (npxg + xa)          / minutes_played::double precision * 90 as npxg_xa_per90,
    big_chances          / minutes_played::double precision * 90 as big_chances_per90,
    dribbles             / minutes_played::double precision * 90 as dribbles_per90,
    dribbles_completed   / minutes_played::double precision * 90 as dribbles_completed_per90,
    miscontrols          / minutes_played::double precision * 90 as miscontrols_per90,
    dispossessed         / minutes_played::double precision * 90 as dispossessed_per90,
    tackles              / minutes_played::double precision * 90 as tackles_per90,
    tackles_won          / minutes_played::double precision * 90 as tackles_won_per90,
    interceptions        / minutes_played::double precision * 90 as interceptions_per90,
    clearances           / minutes_played::double precision * 90 as clearances_per90,
    shot_blocks          / minutes_played::double precision * 90 as shot_blocks_per90,
    pass_blocks          / minutes_played::double precision * 90 as pass_blocks_per90,
    ball_recoveries      / minutes_played::double precision * 90 as ball_recoveries_per90,
    aerials              / minutes_played::double precision * 90 as aerials_per90,
    aerials_won          / minutes_played::double precision * 90 as aerials_won_per90,
    fouls_committed      / minutes_played::double precision * 90 as fouls_committed_per90,
    fouls_won            / minutes_played::double precision * 90 as fouls_won_per90,
    errors               / minutes_played::double precision * 90 as errors_per90,
    saves                / minutes_played::double precision * 90 as saves_per90,

    -- Ratios of sums. NULL, not 0, when nobody attempted the action.
    passes_completed    / nullif(passes, 0)::double precision        * 100 as pass_pct,
    crosses_completed   / nullif(crosses, 0)::double precision       * 100 as cross_pct,
    long_balls_completed / nullif(long_balls, 0)::double precision   * 100 as long_ball_pct,
    through_balls_completed
                        / nullif(through_balls, 0)::double precision * 100 as through_ball_pct,
    dribbles_completed  / nullif(dribbles, 0)::double precision      * 100 as dribble_pct,
    aerials_won         / nullif(aerials, 0)::double precision       * 100 as aerial_pct,
    tackles_won         / nullif(tackles, 0)::double precision       * 100 as tackle_pct,
    shots_on_target     / nullif(shots, 0)::double precision         * 100 as shot_accuracy_pct,

    -- Non-penalty xG per non-penalty shot: shot quality, not volume.
    npxg / nullif(shots - penalties_taken, 0)::double precision           as npxg_per_shot,
    -- Finishing versus expectation. A season total, not a rate.
    non_penalty_goals - npxg                                              as goals_minus_npxg,

    -- Raw totals kept alongside the rates: a report must state the sample,
    -- and day 4 recomputes percentiles from sums rather than from rates.
    goals,
    non_penalty_goals,
    assists,
    npxg,
    xa,
    shots,
    penalties_taken,
    passes,
    passes_completed
from football.player_season;

comment on view football.player_per90 is
    'Per-90 rates and ratio metrics per player per league-season. Per-90 uses '
    'real expanded minutes, so values are 8-11% below nominal-90 sources and '
    'should only be compared within OpenPlay (D-004).';


-- Views inherit SELECT through the default privileges set in 001, but state
-- it explicitly so a reader of this file can see the read-only role's reach.
grant select on football.position_map        to football_ro;
grant select on football.player_season_club  to football_ro;
grant select on football.player_season       to football_ro;
grant select on football.player_per90        to football_ro;
grant execute on function football.position_group(text)       to football_ro;
grant execute on function football.position_group_broad(text) to football_ro;
