"""OpenPlay frames -> database-shaped frames.

Every function here is pure: DataFrame in, DataFrame out, no database and no
network. That is what makes the transform rules unit-testable in milliseconds
(tests/test_extract.py) while the slow parts stay in load.py.

``TABLE_COLUMNS`` is the single source of truth for column order. The loader
COPYs positionally, so order is part of the contract; a database-backed test
asserts these tuples still match the live schema.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

import pandas as pd

TEAM_COLUMNS: tuple[str, ...] = ("team_id", "team", "country", "team_type")

PLAYER_COLUMNS: tuple[str, ...] = (
    "player_id",
    "player",
    "height_cm",
    "weight_kg",
    "birth_year_est",
    "main_position",
)

MATCH_COLUMNS: tuple[str, ...] = (
    "match_id",
    "comp",
    "season",
    "competition",
    "date",
    "kickoff",
    "home_team_id",
    "home_team",
    "away_team_id",
    "away_team",
    "home_score",
    "away_score",
    "home_score_90",
    "away_score_90",
    "home_ht_score",
    "away_ht_score",
    "extra_time",
    "penalty_shootout",
    "home_pk_score",
    "away_pk_score",
    "home_manager",
    "away_manager",
    "home_formation",
    "away_formation",
    "home_avg_age",
    "away_avg_age",
    "home_country",
    "away_country",
    "venue",
    "attendance",
    "referee_id",
    "referee",
    "status_code",
    "max_period",
    "expanded_max_minute",
    "n_events",
    "n_shots",
    "xg_model",
    "score_matches_events",
)

LINEUP_COLUMNS: tuple[str, ...] = (
    "match_id",
    "player_id",
    "comp",
    "season",
    "team_id",
    "side",
    "opponent_id",
    "shirt_no",
    "position",
    "is_starter",
    "played",
    "minute_on",
    "minute_off",
    "minutes_played",
    "subbed_on",
    "subbed_off",
    "sent_off",
    "is_captain_start",
    "was_captain",
    "age",
)

PLAYER_MATCH_STATS_COLUMNS: tuple[str, ...] = (
    "match_id",
    "player_id",
    "comp",
    "season",
    "date",
    "team_id",
    "team",
    "opponent_id",
    "opponent",
    "side",
    "player",
    "position",
    "is_starter",
    "played",
    "minute_on",
    "minute_off",
    "minutes_played",
    "touches",
    "passes",
    "passes_completed",
    "pass_pct",
    "passes_final_third",
    "passes_into_box",
    "progressive_passes",
    "crosses",
    "crosses_completed",
    "long_balls",
    "long_balls_completed",
    "through_balls",
    "through_balls_completed",
    "headed_passes",
    "chipped_passes",
    "layoffs",
    "key_passes",
    "assists",
    "xa",
    "big_chances_created",
    "corners_taken",
    "free_kicks_taken",
    "throw_ins",
    "goal_kicks",
    "keeper_throws",
    "shots",
    "shots_on_target",
    "shots_off_target",
    "shots_blocked",
    "shots_on_post",
    "shots_inside_box",
    "shots_outside_box",
    "headed_shots",
    "goals",
    "headed_goals",
    "penalty_goals",
    "penalties_taken",
    "penalties_missed",
    "own_goals",
    "non_penalty_goals",
    "xg",
    "npxg",
    "big_chances",
    "big_chances_missed",
    "goals_disallowed",
    "dribbles",
    "dribbles_completed",
    "dribbled_past",
    "miscontrols",
    "dispossessed",
    "tackles",
    "tackles_won",
    "interceptions",
    "clearances",
    "shot_blocks",
    "pass_blocks",
    "ball_recoveries",
    "aerials",
    "aerials_won",
    "fouls_committed",
    "fouls_won",
    "offsides",
    "offsides_provoked",
    "errors",
    "errors_leading_to_shot",
    "errors_leading_to_goal",
    "saves",
    "claims",
    "claims_failed",
    "punches",
    "keeper_sweeper",
    "smothers",
    "keeper_pickups",
    "shootout_penalties_taken",
    "shootout_penalties_scored",
    "yellow_cards",
    "second_yellows",
    "red_cards",
)

SHOT_COLUMNS: tuple[str, ...] = (
    "match_id",
    "event_id",
    "event_id_sub",
    "comp",
    "season",
    "team_event_id",
    "period",
    "minute",
    "second",
    "expanded_minute",
    "team_id",
    "is_home",
    "opponent_id",
    "player_id",
    "result",
    "is_goal",
    "is_own_goal",
    "is_on_target",
    "is_blocked",
    "is_penalty",
    "is_shootout",
    "is_big_chance",
    "is_header",
    "body_part",
    "play_pattern",
    "shot_zone",
    "shot_target",
    "is_set_piece",
    "is_fast_break",
    "is_volley",
    "is_first_touch",
    "is_one_on_one",
    "is_assisted",
    "is_individual_play",
    "is_disallowed",
    "x",
    "y",
    "distance_m",
    "visible_angle",
    "goal_mouth_y",
    "goal_mouth_z",
    "blocked_x",
    "blocked_y",
    "xg",
    "assist_player_id",
    "assist_type",
    "assist_event_type",
    "assist_event_id",
    "xg_model",
)

PASS_COLUMNS: tuple[str, ...] = (
    "match_id",
    "event_id",
    "event_id_sub",
    "comp",
    "season",
    "team_id",
    "player_id",
    "period",
    "minute",
    "second",
    "expanded_minute",
    "x",
    "y",
    "end_x",
    "end_y",
    "outcome",
    "is_completed",
    "pass_length",
    "pass_angle",
    "zone",
    "is_cross",
    "is_long_ball",
    "is_through_ball",
    "is_key_pass",
    "is_chipped",
    "is_head_pass",
    "is_throw_in",
    "is_corner",
    "is_freekick",
    "is_layoff",
    "is_intentional_assist",
)

DATA_QUALITY_COLUMNS: tuple[str, ...] = (
    "run_at",
    "data_tag",
    "comp",
    "season",
    "metric",
    "value",
    "target",
    "critical_floor",
    "status",
)

DATA_QUALITY_FEATURE_COLUMNS: tuple[str, ...] = ("run_at", "data_tag", "feature", "status")

METRIC_DEFINITION_COLUMNS: tuple[str, ...] = (
    "key",
    "source_column",
    "label",
    "definition",
    "formula",
    "unit",
    "higher_is_better",
    "category",
    "sort_order",
)

METRIC_CONFIG_COLUMNS: tuple[str, ...] = ("key", "value")

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "teams": TEAM_COLUMNS,
    "players": PLAYER_COLUMNS,
    "matches": MATCH_COLUMNS,
    "lineups": LINEUP_COLUMNS,
    "player_match_stats": PLAYER_MATCH_STATS_COLUMNS,
    "shots": SHOT_COLUMNS,
    "passes": PASS_COLUMNS,
    "data_quality": DATA_QUALITY_COLUMNS,
    "data_quality_features": DATA_QUALITY_FEATURE_COLUMNS,
    "metric_definitions": METRIC_DEFINITION_COLUMNS,
    "metric_config": METRIC_CONFIG_COLUMNS,
}

# Load order matters: dimensions before the facts that reference them.
LOAD_ORDER: tuple[str, ...] = (
    "teams",
    "players",
    "matches",
    "lineups",
    "player_match_stats",
    "shots",
    "passes",
)

# Source qualifier name -> our column name. Renaming is a text-to-SQL feature:
# a model has no idea what `q_Longball` is, but `is_long_ball` is self-evident.
PASS_QUALIFIER_RENAMES: dict[str, str] = {
    "q_Length": "pass_length",
    "q_Angle": "pass_angle",
    "q_Zone": "zone",
    "q_Cross": "is_cross",
    "q_Longball": "is_long_ball",
    "q_Throughball": "is_through_ball",
    "q_KeyPass": "is_key_pass",
    "q_Chipped": "is_chipped",
    "q_HeadPass": "is_head_pass",
    "q_ThrowIn": "is_throw_in",
    "q_CornerTaken": "is_corner",
    "q_FreekickTaken": "is_freekick",
    "q_LayOff": "is_layoff",
    "q_IntentionalAssist": "is_intentional_assist",
}

# Thresholds mirrored from scripts/validate_openplay.py so data_quality rows
# carry the target they were judged against, not just the verdict.
DQ_TARGETS: dict[str, float] = {
    "match_coverage_pct": 99.0,
    "shot_xg_filled_pct": 99.0,
    "pass_end_xy_filled_pct": 99.0,
    "coords_out_of_range": 0.0,
    "score_mismatch_pct": 1.0,
    "unknown_minutes_pct": 1.0,
}
DQ_CRITICAL: dict[str, float] = {
    "shot_xg_filled_pct": 90.0,
    "pass_end_xy_filled_pct": 90.0,
    "match_coverage_pct": 95.0,
}


def _project(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Select ``columns`` in order, failing loudly on anything missing."""
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        msg = f"source frame is missing expected columns: {missing}"
        raise ValueError(msg)
    return frame.loc[:, list(columns)].copy()


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def extract_matches(matches: pd.DataFrame) -> pd.DataFrame:
    out = matches.copy()
    # Day 1 rule: the flag is nullable and null means "no mismatch detected".
    out["score_matches_events"] = out["score_matches_events"].fillna(True).astype(bool)
    # Source stores kickoff as an ISO string with no timezone, so a naive
    # timestamp is the honest representation.
    out["kickoff"] = pd.to_datetime(out["kickoff"], errors="coerce")
    return _project(out, MATCH_COLUMNS)


def extract_lineups(lineups: pd.DataFrame) -> pd.DataFrame:
    return _project(lineups, LINEUP_COLUMNS)


def extract_player_match_stats(stats: pd.DataFrame) -> pd.DataFrame:
    # `in_lineup` is true for every source row (day 1 finding), so it is not
    # loaded; _project drops it by omission.
    return _project(stats, PLAYER_MATCH_STATS_COLUMNS)


def extract_shots(shots: pd.DataFrame) -> pd.DataFrame:
    return _project(shots, SHOT_COLUMNS)


def extract_passes(events: pd.DataFrame) -> pd.DataFrame:
    """Curated pass table from the raw event stream.

    Only ``type == 'Pass'`` rows survive. Within that subset
    (match_id, event_id, event_id_sub) is unique, which is why it can be the
    primary key even though the full event stream has 82 id collisions between
    OffsideGiven events and unrelated events.
    """
    passes = events.loc[events["type"] == "Pass"].copy()
    passes = passes.rename(columns=PASS_QUALIFIER_RENAMES)
    # A boolean beats remembering the exact string literal in a WHERE clause.
    passes["is_completed"] = passes["outcome"].astype("string").eq("Successful")
    return _project(passes, PASS_COLUMNS)


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

_PLAYER_ID_COLUMNS = ("player_id", "assist_player_id")
_TEAM_ID_COLUMNS = ("team_id", "opponent_id", "home_team_id", "away_team_id")


def _collect_ids(frames: Iterable[pd.DataFrame], columns: Sequence[str]) -> set[int]:
    ids: set[int] = set()
    for frame in frames:
        for column in columns:
            if column in frame.columns:
                ids.update(int(v) for v in frame[column].dropna().unique())
    return ids


def referenced_player_ids(frames: Iterable[pd.DataFrame]) -> set[int]:
    """Every player id any fact row points at, assisters included.

    Missing an assister would break the shots.assist_player_id foreign key.
    """
    return _collect_ids(frames, _PLAYER_ID_COLUMNS)


def referenced_team_ids(frames: Iterable[pd.DataFrame]) -> set[int]:
    return _collect_ids(frames, _TEAM_ID_COLUMNS)


def _filter_dimension(
    frame: pd.DataFrame, ids: set[int], key: str, columns: Sequence[str], label: str
) -> pd.DataFrame:
    """Keep only referenced rows, and refuse to proceed if any id is absent.

    Failing here with a readable message is much better than a foreign key
    violation partway through a million-row COPY.
    """
    available = set(frame[key].dropna().astype(int))
    missing = sorted(ids - available)
    if missing:
        msg = f"{label}: {len(missing)} referenced id(s) absent from the source, e.g. {missing[:5]}"
        raise ValueError(msg)
    out = frame.loc[frame[key].isin(ids)].copy()
    return _project(out, columns).sort_values(key, ignore_index=True)


def extract_teams(teams: pd.DataFrame, ids: set[int]) -> pd.DataFrame:
    """Teams referenced by our three leagues only.

    The source table is global (422 rows across every competition), and an
    unfiltered copy would make "how many teams are there" a misleading answer.
    """
    return _filter_dimension(teams, ids, "team_id", TEAM_COLUMNS, "teams")


def extract_players(players: pd.DataFrame, ids: set[int]) -> pd.DataFrame:
    """Players referenced by our three leagues only (source has 20 782)."""
    return _filter_dimension(players, ids, "player_id", PLAYER_COLUMNS, "players")


# ---------------------------------------------------------------------------
# Data quality report -> rows
# ---------------------------------------------------------------------------


def extract_data_quality(
    report: dict, *, data_tag: str, run_at: datetime | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flatten reports/data_validation_2526.json into two tidy frames.

    Tidy rows rather than a jsonb blob: from day 13 the agent asks "is xG
    analysis enabled?" in SQL, and `jsonb ->>` is exactly the construct models
    get wrong.

    ``run_at`` identifies the *report*, not the load. It comes from the
    report's own ``generated_at`` so that loading the same report twice
    produces the same rows; falling back to the current time would make the
    load non-idempotent. Unlike the frozen fact tables, these rows accumulate:
    each validation run is a new point in a history we want to keep.
    """
    stamp = run_at
    if stamp is None:
        generated = report.get("generated_at")
        stamp = (
            datetime.fromisoformat(generated).astimezone(UTC) if generated else datetime.now(UTC)
        )
    season = report.get("season", "2526")

    metric_rows = []
    for comp, result in report["results"].items():
        for metric, value in result["metrics"].items():
            metric_rows.append(
                {
                    "run_at": stamp,
                    "data_tag": data_tag,
                    "comp": comp,
                    "season": season,
                    "metric": metric,
                    "value": float(value),
                    "target": DQ_TARGETS.get(metric),
                    "critical_floor": DQ_CRITICAL.get(metric),
                    "status": result["status"][metric],
                }
            )
    metrics = pd.DataFrame(metric_rows, columns=list(DATA_QUALITY_COLUMNS))

    feature_rows = [
        {"run_at": stamp, "data_tag": data_tag, "feature": feature, "status": status}
        for feature, status in report["feature_flags"].items()
    ]
    features = pd.DataFrame(feature_rows, columns=list(DATA_QUALITY_FEATURE_COLUMNS))
    return metrics, features
