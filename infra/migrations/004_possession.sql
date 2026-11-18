-- 004_possession.sql
--
-- Day 7: a possession proxy for the possession-adjusted (PAdj) defensive
-- metrics in the player profile. No `possession` column exists anywhere in
-- the schema (checked player_match_stats, matches, passes, shots), so the
-- proxy is touches share: a team's fraction of total touches in a match,
-- the same proxy FBref/Wyscout use when no tracking data is available.
--
-- team_match_touches -> match_possession -> player_possession is three
-- views because each step needs its own grouping: touches per team per
-- match, then paired against the opponent in the same match, then
-- minutes-weighted across every match a player actually appeared in.

create or replace view football.team_match_touches as
select
    match_id,
    team_id,
    sum(touches)::double precision as team_touches
from football.player_match_stats
group by match_id, team_id;

comment on view football.team_match_touches is
    'One row per team per match: total touches, the possession proxy input.';

create or replace view football.match_possession as
select
    a.match_id,
    a.team_id,
    b.team_id as opponent_id,
    a.team_touches / nullif(a.team_touches + b.team_touches, 0) * 100
        as team_possession_pct,
    b.team_touches / nullif(a.team_touches + b.team_touches, 0) * 100
        as opponent_possession_pct
from football.team_match_touches a
join football.team_match_touches b
    on b.match_id = a.match_id and b.team_id <> a.team_id;

comment on view football.match_possession is
    'One row per team per match, paired against the opponent in that same '
    'match: touches-share possession proxy for both sides. The two '
    'percentages sum to 100 by construction.';

create or replace view football.player_possession as
select
    pms.comp,
    pms.season,
    pms.player_id,
    sum(mp.opponent_possession_pct * pms.minutes_played)
        / nullif(sum(pms.minutes_played), 0) as avg_opponent_possession_pct
from football.player_match_stats pms
join football.match_possession mp
    on mp.match_id = pms.match_id and mp.team_id = pms.team_id
group by pms.comp, pms.season, pms.player_id;

comment on view football.player_possession is
    'Minutes-weighted average opponent possession (touches-share proxy) '
    'across the matches a player appeared in, per comp+season. Feeds the '
    'PAdj correction on category=''defending'' metrics in the player '
    'profile: PAdj = raw_per90 * 50 / avg_opponent_possession_pct. NULL '
    'when minutes_played sums to zero across the player''s matches.';

grant select on football.team_match_touches to football_ro;
grant select on football.match_possession    to football_ro;
grant select on football.player_possession   to football_ro;
