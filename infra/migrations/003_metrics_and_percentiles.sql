-- 003_metrics_and_percentiles.sql
--
-- Day 4: metric definitions as data, and percentiles within a comparison
-- group. See DECISIONS.md D-018..D-020.
--
-- config/metrics.yaml is the source of truth. The ETL loads it into
-- metric_definitions and metric_config; player_metrics computes values and
-- percentiles live. Changing a threshold in the yaml therefore changes
-- behaviour without a migration, which is the point of having a config file.

-- ===========================================================================
-- Definitions, loaded from config/metrics.yaml
-- ===========================================================================

create table football.metric_definitions (
    key               text primary key,
    source_column     text not null,
    label             text not null,
    definition        text not null,
    formula           text not null,
    -- per90 | percent | ratio | count
    unit              text not null,
    -- false for miscontrols, dispossessed, fouls committed, errors. The
    -- percentile is oriented by this flag so that 100 always means "best".
    higher_is_better  boolean not null,
    category          text not null,
    sort_order        int not null
);

comment on table football.metric_definitions is
    'Loaded from config/metrics.yaml by the ETL. Every metric carries its '
    'formula, unit and direction so a report can state them without guessing.';

create table football.metric_config (
    key   text primary key,
    value double precision not null
);

comment on table football.metric_config is
    'Thresholds from config/metrics.yaml: min_minutes, min_group_size.';


-- ===========================================================================
-- player_metrics: one row per player per metric, long format.
--
-- Long rather than one column per metric. Adding a metric then means editing
-- the yaml and this VALUES list, not altering a 40-column view; filtering is
-- `where metric = 'npxg_per90'`, which is easier for a model to get right
-- than remembering column names; and the comparison group size, which every
-- scouting report has to state, is a column rather than something the caller
-- recomputes.
--
-- Rows with a NULL value are not emitted. A NULL here means "not applicable"
-- (no passes attempted, so no pass accuracy), and ranking a player who never
-- attempted the action against players who did would be meaningless.
-- ===========================================================================

create or replace view football.player_metrics as
with cfg as (
    select
        (select value from football.metric_config where key = 'min_minutes')    as min_minutes,
        (select value from football.metric_config where key = 'min_group_size') as min_group_size
),
qualified as (
    select p.*
    from football.player_per90 p, cfg
    where p.minutes_played >= cfg.min_minutes
),
long as (
    select
        q.comp, q.season, q.player_id, q.player, q.teams,
        q.position_group, q.position_group_broad,
        q.minutes_played, q.matches,
        m.metric, m.value
    from qualified q
    cross join lateral (values
        ('npxg_per90',                q.npxg_per90),
        ('non_penalty_goals_per90',   q.non_penalty_goals_per90),
        ('shots_per90',               q.shots_per90),
        ('shots_on_target_per90',     q.shots_on_target_per90),
        ('npxg_per_shot',             q.npxg_per_shot),
        ('shot_accuracy_pct',         q.shot_accuracy_pct),
        ('goals_minus_npxg',          q.goals_minus_npxg),
        ('xa_per90',                  q.xa_per90),
        ('npxg_xa_per90',             q.npxg_xa_per90),
        ('assists_per90',             q.assists_per90),
        ('key_passes_per90',          q.key_passes_per90),
        ('big_chances_created_per90', q.big_chances_created_per90),
        ('crosses_per90',             q.crosses_per90),
        ('cross_pct',                 q.cross_pct),
        ('passes_per90',              q.passes_per90),
        ('pass_pct',                  q.pass_pct),
        ('long_balls_per90',          q.long_balls_per90),
        ('long_ball_pct',             q.long_ball_pct),
        ('through_balls_per90',       q.through_balls_per90),
        ('progressive_passes_per90',  q.progressive_passes_per90),
        ('passes_final_third_per90',  q.passes_final_third_per90),
        ('passes_into_box_per90',     q.passes_into_box_per90),
        ('dribbles_completed_per90',  q.dribbles_completed_per90),
        ('dribble_pct',               q.dribble_pct),
        ('tackles_per90',             q.tackles_per90),
        ('tackle_pct',                q.tackle_pct),
        ('interceptions_per90',       q.interceptions_per90),
        ('ball_recoveries_per90',     q.ball_recoveries_per90),
        ('clearances_per90',          q.clearances_per90),
        ('shot_blocks_per90',         q.shot_blocks_per90),
        ('aerials_per90',             q.aerials_per90),
        ('aerial_pct',                q.aerial_pct),
        ('fouls_won_per90',           q.fouls_won_per90),
        ('miscontrols_per90',         q.miscontrols_per90),
        ('dispossessed_per90',        q.dispossessed_per90),
        ('fouls_committed_per90',     q.fouls_committed_per90),
        ('errors_per90',              q.errors_per90),
        ('saves_per90',               q.saves_per90)
    ) as m(metric, value)
    where m.value is not null
),
ranked as (
    select
        l.*,
        -- Within league + fine position group: the preferred comparison.
        percent_rank() over w_league as pr_league,
        cume_dist()    over w_league as cd_league,
        -- The counting windows deliberately carry no ORDER BY. An ordered
        -- window defaults to the frame RANGE UNBOUNDED PRECEDING ... CURRENT
        -- ROW, so count(*) over it returns a running count, not the partition
        -- size - it reads 1 for the lowest-valued player in every group.
        -- percent_rank and cume_dist are rank functions and ignore the frame,
        -- which is why only the counts were wrong.
        count(*)       over c_league as n_league,
        -- Same role, leagues pooled: the fallback when a league cell is thin.
        percent_rank() over w_pooled as pr_pooled,
        cume_dist()    over w_pooled as cd_pooled,
        count(*)       over c_pooled as n_pooled
    from long l
    window
        w_league as (partition by l.metric, l.comp, l.position_group order by l.value),
        c_league as (partition by l.metric, l.comp, l.position_group),
        w_pooled as (partition by l.metric, l.position_group order by l.value),
        c_pooled as (partition by l.metric, l.position_group)
),
scoped as (
    select
        r.*,
        (r.n_league >= cfg.min_group_size) as use_league,
        -- Even the pooled group can be too small: a metric is only defined
        -- for players who attempted the action, so cross_pct loses 101 of
        -- 1 072 players. Below the threshold no percentile is reported at
        -- all - a rank out of three players is not information.
        (greatest(r.n_league, r.n_pooled) >= cfg.min_group_size) as rankable
    from ranked r, cfg
)
select
    s.comp,
    s.season,
    s.player_id,
    s.player,
    s.teams,
    s.position_group,
    s.position_group_broad,
    s.minutes_played,
    s.matches,
    s.metric,
    d.label,
    d.unit,
    d.category,
    d.higher_is_better,
    s.value,
    -- Midrank percentile, (rank - 0.5) / n, expressed through the built-ins
    -- so ties are handled: percent_rank x (n-1) counts the players strictly
    -- below, cume_dist x n counts those below or equal, and the mean of the
    -- two is the tie-aware midrank. Neither the worst nor the best player is
    -- handed an absolute 0 or 100.
    --
    -- Then oriented by direction, so 100 always means "best in the group",
    -- including for miscontrols and fouls where a low raw value is good.
    case
        when not s.rankable then null
        else
            case when d.higher_is_better then 1 else -1 end
            * (case
                   when s.use_league then
                       100.0 * (s.pr_league * (s.n_league - 1) + s.cd_league * s.n_league)
                             / (2.0 * s.n_league)
                   else
                       100.0 * (s.pr_pooled * (s.n_pooled - 1) + s.cd_pooled * s.n_pooled)
                             / (2.0 * s.n_pooled)
               end)
            + case when d.higher_is_better then 0 else 100 end
    end as percentile,
    case
        when not s.rankable then 'insufficient'
        when s.use_league   then 'league_position'
        else 'position_pooled'
    end as comparison_scope,
    case
        when not s.rankable then null
        when s.use_league   then s.comp
        else 'all'
    end as comparison_comp,
    case when s.use_league then s.n_league else s.n_pooled end
        as comparison_group_size,
    d.formula,
    d.definition
from scoped s
join football.metric_definitions d on d.key = s.metric;

comment on view football.player_metrics is
    'One row per qualified player per metric: value, percentile (100 = best in '
    'the comparison group, already oriented for lower-is-better metrics), and '
    'the comparison group with its size. Metrics whose value is NULL are '
    'omitted rather than ranked. The value is always present; percentile is '
    'NULL when comparison_scope is ''insufficient'', meaning too few comparable '
    'players to rank against.';

grant select on football.metric_definitions to football_ro;
grant select on football.metric_config      to football_ro;
grant select on football.player_metrics     to football_ro;
