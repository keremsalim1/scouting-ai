-- 001_schema.sql — OpenPlay 2025/26 relational model.
--
-- Design notes (see DECISIONS.md D-008..D-011):
--  * Everything lives in schema `football`, never `public`. The day-5 SQL
--    allowlist is then "schema football, these tables", and `public` can be
--    locked down wholesale.
--  * `comp` and `season` are denormalised onto every fact table. The most
--    common filter in a scouting query is league + season; paying for it with
--    two small columns instead of a join measurably helps text-to-SQL.
--  * Label columns (player/team/opponent names) are denormalised for the same
--    reason. Safe here because the season is finished and the ETL is a full
--    reload, so the copies cannot drift from their dimension rows.
--  * Natural keys throughout, all verified unique against the source before
--    being written here. No surrogate keys: the source ids are stable
--    integers, and an extra layer would only be something the LLM has to learn.
--  * Foreign keys are declared deliberately. Besides integrity, day 5 builds
--    the schema description from the Postgres catalog, and FKs are what tell
--    the model how tables join.

create schema if not exists football;

-- pgvector is needed from day 8 (similarity vectors). Enabling it now avoids
-- touching the container image later; it costs nothing while unused.
create extension if not exists vector;

-- Nobody gets to create objects in public.
revoke all on schema public from public;


-- ===========================================================================
-- Dimensions
-- ===========================================================================

-- Only teams/players actually referenced by the three leagues we load.
-- The source tables are global (422 teams, 20 782 players across every
-- competition and season), and an unfiltered copy would make
-- "how many players are in the database" a misleading answer.
create table football.teams (
    team_id                            integer primary key,
    team                               text not null,
    country                            text,
    team_type                          text
);

create table football.players (
    player_id                          integer primary key,
    player                             text not null,
    height_cm                          smallint,
    weight_kg                          smallint,
    birth_year_est                     smallint,
    main_position                      text
);


-- ===========================================================================
-- Matches
-- ===========================================================================

create table football.matches (
    match_id                           integer primary key,
    comp                               text not null,
    season                             text not null,
    competition                        text,
    date                               date not null,
    kickoff                            timestamp,
    home_team_id                       integer not null references football.teams,
    home_team                          text,
    away_team_id                       integer not null references football.teams,
    away_team                          text,
    home_score                         smallint,
    away_score                         smallint,
    home_score_90                      smallint,
    away_score_90                      smallint,
    home_ht_score                      smallint,
    away_ht_score                      smallint,
    extra_time                         boolean,
    penalty_shootout                   boolean,
    home_pk_score                      smallint,
    away_pk_score                      smallint,
    home_manager                       text,
    away_manager                       text,
    home_formation                     text,
    away_formation                     text,
    home_avg_age                       real,
    away_avg_age                       real,
    home_country                       text,
    away_country                       text,
    venue                              text,
    attendance                         integer,
    referee_id                         integer,
    referee                            text,
    status_code                        smallint,
    max_period                         smallint,
    -- Match length in expanded (stoppage-inclusive) minutes: 98-101, not 90.
    expanded_max_minute                smallint,
    n_events                           integer,
    n_shots                            integer,
    xg_model                           text,
    -- Nullable in the source; the ETL resolves null to true (day 1 finding).
    score_matches_events               boolean
);

create index on football.matches (comp, season);
create index on football.matches (date);


-- ===========================================================================
-- Lineups — the full matchday squad, including unused substitutes.
-- `played = true` matches player_match_stats row-for-row (verified: 11 492 /
-- 11 953 / 11 928). `sent_off` explains why team minutes fall below
-- 11 x match length in some matches.
-- ===========================================================================

create table football.lineups (
    match_id                           integer not null references football.matches,
    player_id                          integer not null references football.players,
    comp                               text not null,
    season                             text not null,
    team_id                            integer not null references football.teams,
    side                               text,
    opponent_id                        integer references football.teams,
    shirt_no                           smallint,
    -- Starting position; 'Sub' for players who came on (day 1 finding, D-005).
    position                           text,
    is_starter                         boolean,
    played                             boolean,
    minute_on                          smallint,
    minute_off                         smallint,
    minutes_played                     smallint,
    subbed_on                          boolean,
    subbed_off                         boolean,
    sent_off                           boolean,
    is_captain_start                   boolean,
    was_captain                        boolean,
    age                                smallint,
    primary key (match_id, player_id)
);

create index on football.lineups (comp, season);
create index on football.lineups (player_id);
create index on football.lineups (team_id);


-- ===========================================================================
-- Player match stats — one row per player who actually appeared.
-- The source `in_lineup` column is dropped: it is true for every row, which
-- is why day 1's unknown_minutes_pct check could never fail (D-003).
-- ===========================================================================

create table football.player_match_stats (
    match_id                           integer not null references football.matches,
    player_id                          integer not null references football.players,
    comp                               text not null,
    season                             text not null,
    date                               date,
    team_id                            integer not null references football.teams,
    team                               text,
    opponent_id                        integer references football.teams,
    opponent                           text,
    side                               text,
    player                             text,
    position                           text,
    is_starter                         boolean,
    played                             boolean,
    minute_on                          smallint,
    minute_off                         smallint,
    -- Expanded minutes: a full match is ~98-101, not 90. All per-90 metrics
    -- divide by this, which is why they sit 8-11% below nominal-90 sources.
    minutes_played                     smallint not null,
    touches                            smallint,
    passes                             smallint,
    passes_completed                   smallint,
    pass_pct                           real,
    passes_final_third                 smallint,
    passes_into_box                    smallint,
    progressive_passes                 smallint,
    crosses                            smallint,
    crosses_completed                  smallint,
    long_balls                         smallint,
    long_balls_completed               smallint,
    through_balls                      smallint,
    through_balls_completed            smallint,
    headed_passes                      smallint,
    chipped_passes                     smallint,
    layoffs                            smallint,
    key_passes                         smallint,
    assists                            smallint,
    xa                                 real,
    big_chances_created                smallint,
    corners_taken                      smallint,
    free_kicks_taken                   smallint,
    throw_ins                          smallint,
    goal_kicks                         smallint,
    keeper_throws                      smallint,
    shots                              smallint,
    shots_on_target                    smallint,
    shots_off_target                   smallint,
    shots_blocked                      smallint,
    shots_on_post                      smallint,
    shots_inside_box                   smallint,
    shots_outside_box                  smallint,
    headed_shots                       smallint,
    goals                              smallint,
    headed_goals                       smallint,
    penalty_goals                      smallint,
    penalties_taken                    smallint,
    penalties_missed                   smallint,
    own_goals                          smallint,
    non_penalty_goals                  smallint,
    xg                                 real,
    npxg                               real,
    big_chances                        smallint,
    big_chances_missed                 smallint,
    goals_disallowed                   smallint,
    dribbles                           smallint,
    dribbles_completed                 smallint,
    dribbled_past                      smallint,
    miscontrols                        smallint,
    dispossessed                       smallint,
    tackles                            smallint,
    tackles_won                        smallint,
    interceptions                      smallint,
    clearances                         smallint,
    shot_blocks                        smallint,
    pass_blocks                        smallint,
    ball_recoveries                    smallint,
    aerials                            smallint,
    aerials_won                        smallint,
    fouls_committed                    smallint,
    fouls_won                          smallint,
    offsides                           smallint,
    offsides_provoked                  smallint,
    errors                             smallint,
    errors_leading_to_shot             smallint,
    errors_leading_to_goal             smallint,
    saves                              smallint,
    claims                             smallint,
    claims_failed                      smallint,
    punches                            smallint,
    keeper_sweeper                     smallint,
    smothers                           smallint,
    keeper_pickups                     smallint,
    shootout_penalties_taken           smallint,
    shootout_penalties_scored          smallint,
    yellow_cards                       smallint,
    second_yellows                     smallint,
    red_cards                          smallint,
    primary key (match_id, player_id)
);

create index on football.player_match_stats (comp, season);
create index on football.player_match_stats (player_id);
create index on football.player_match_stats (team_id);
-- Covers the day 3/4 aggregation path: per-league season totals per player.
create index on football.player_match_stats (comp, season, player_id, team_id);


-- ===========================================================================
-- Shots
-- ===========================================================================

create table football.shots (
    match_id                           integer not null references football.matches,
    event_id                           bigint not null,
    event_id_sub                       smallint not null,
    comp                               text not null,
    season                             text not null,
    team_event_id                      integer,
    period                             text,
    minute                             smallint,
    second                             smallint,
    expanded_minute                    smallint,
    team_id                            integer not null references football.teams,
    is_home                            boolean,
    opponent_id                        integer references football.teams,
    player_id                          integer references football.players,
    result                             text,
    is_goal                            boolean,
    is_own_goal                        boolean,
    is_on_target                       boolean,
    is_blocked                         boolean,
    is_penalty                         boolean,
    is_shootout                        boolean,
    is_big_chance                      boolean,
    is_header                          boolean,
    body_part                          text,
    play_pattern                       text,
    shot_zone                          text,
    shot_target                        text,
    is_set_piece                       boolean,
    is_fast_break                      boolean,
    is_volley                          boolean,
    is_first_touch                     boolean,
    is_one_on_one                      boolean,
    is_assisted                        boolean,
    is_individual_play                 boolean,
    is_disallowed                      boolean,
    -- Coordinates are 0-100 and every team attacks towards x=100.
    -- Metres: x * 1.05, y * 0.68.
    x                                  real,
    y                                  real,
    distance_m                         real,
    visible_angle                      real,
    goal_mouth_y                       real,
    goal_mouth_z                       real,
    blocked_x                          real,
    blocked_y                          real,
    xg                                 real,
    assist_player_id                   integer references football.players,
    assist_type                        text,
    assist_event_type                  text,
    assist_event_id                    bigint,
    xg_model                           text,
    primary key (match_id, event_id, event_id_sub)
);

create index on football.shots (comp, season);
create index on football.shots (player_id);
create index on football.shots (team_id);


-- ===========================================================================
-- Passes — derived from events where type = 'Pass' (~1.08M rows).
--
-- The raw events table is deliberately NOT loaded: 152 columns of which most
-- are source-specific qualifier flags. `passes` and `shots` are the curated
-- extracts; other event types get their own table when a day needs them.
--
-- Qualifier columns are renamed from `q_Cross` to `is_cross` and friends.
-- Column naming is a text-to-SQL feature: `q_Cross` means nothing to a model,
-- `is_cross` is self-evident. `q_Assisted` is dropped (always false on passes).
--
-- The source reuses event_id between an OffsideGiven event and an unrelated
-- event in the same match (82 collisions across the three leagues), so
-- (match_id, event_id, event_id_sub) is NOT unique over all events. It IS
-- unique within type = 'Pass', which is what this table holds.
-- ===========================================================================

create table football.passes (
    match_id                           integer not null references football.matches,
    event_id                           bigint not null,
    event_id_sub                       smallint not null,
    comp                               text not null,
    season                             text not null,
    team_id                            integer not null references football.teams,
    player_id                          integer references football.players,
    period                             text,
    minute                             smallint,
    second                             smallint,
    expanded_minute                    smallint,
    x                                  real,
    y                                  real,
    end_x                              real,
    end_y                              real,
    outcome                            text,
    is_completed                       boolean,
    pass_length                        real,
    pass_angle                         real,
    zone                               text,
    is_cross                           boolean,
    is_long_ball                       boolean,
    is_through_ball                    boolean,
    is_key_pass                        boolean,
    is_chipped                         boolean,
    is_head_pass                       boolean,
    is_throw_in                        boolean,
    is_corner                          boolean,
    is_freekick                        boolean,
    is_layoff                          boolean,
    is_intentional_assist              boolean,
    primary key (match_id, event_id, event_id_sub)
);

create index on football.passes (comp, season);
create index on football.passes (player_id);
create index on football.passes (team_id);
create index on football.passes (match_id);


-- ===========================================================================
-- Data quality — the day 1 validation report, as queryable rows.
--
-- Stored tidy (one row per comp x metric) rather than as a jsonb blob: from
-- day 13 the agent must ask "is xG analysis enabled?" in SQL, and `jsonb ->>`
-- is exactly the construct models get wrong. Run metadata is repeated on each
-- row so the common query needs no join.
-- ===========================================================================

create table football.data_quality (
    run_at                             timestamptz not null,
    data_tag                           text not null,
    comp                               text not null,
    season                             text not null,
    metric                             text not null,
    value                              double precision,
    target                             double precision,
    critical_floor                     double precision,
    status                             text not null check (status in ('pass', 'degraded', 'disabled')),
    primary key (run_at, comp, season, metric)
);

create index on football.data_quality (metric);
create index on football.data_quality (status);

create table football.data_quality_features (
    run_at                             timestamptz not null,
    data_tag                           text not null,
    feature                            text not null,
    status                             text not null check (status in ('pass', 'degraded', 'disabled')),
    primary key (run_at, feature)
);


-- ===========================================================================
-- Read-only role for the day-5 SQL agent.
--
-- The role is created by scripts/migrate.py (it needs the password from the
-- environment, which must not live in a committed file). Here we only grant.
-- `statement_timeout` is set on the role itself, so it is enforced
-- server-side: no client, and no prompt-injected query, can opt out of it.
-- ===========================================================================

grant usage on schema football to football_ro;
grant select on all tables in schema football to football_ro;

-- Views added on day 3 and tables added later inherit SELECT automatically.
alter default privileges in schema football grant select on tables to football_ro;

-- Explicitly deny everything else.
revoke create on schema football from football_ro;
