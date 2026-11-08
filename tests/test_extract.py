"""Unit tests for the pure extract/transform layer.

These build tiny synthetic frames instead of touching OpenPlay, so they run in
milliseconds and pin the transform rules rather than the data. Anything that
needs the real dataset or a database lives in test_etl_db.py.
"""

from __future__ import annotations

import pandas as pd
import pytest

from football_ai.data import extract as ex

# ---------------------------------------------------------------------------
# passes: the most transform-heavy table
# ---------------------------------------------------------------------------


def _events() -> pd.DataFrame:
    """Two passes and two non-pass events, with the qualifier columns we keep."""
    base = {
        "match_id": [1, 1, 1, 1],
        "event_id": [10, 11, 12, 11],
        "event_id_sub": [0, 0, 0, 1],
        "comp": ["eng"] * 4,
        "season": ["2526"] * 4,
        "team_id": [100, 100, 200, 200],
        "player_id": [7, 8, None, 9],
        "type": ["Pass", "Pass", "Aerial", "OffsideGiven"],
        "period": ["FirstHalf"] * 4,
        "minute": [1, 2, 3, 4],
        "second": [0, 10, 20, 30],
        "expanded_minute": [1, 2, 3, 4],
        "x": [50.0, 60.0, 70.0, 80.0],
        "y": [50.0, 40.0, 30.0, 20.0],
        "end_x": [55.0, 65.0, None, None],
        "end_y": [45.0, 35.0, None, None],
        "outcome": ["Successful", "Unsuccessful", "Successful", "Unsuccessful"],
        "q_Length": [12.5, 30.0, 0.0, 0.0],
        "q_Angle": [1.1, 2.2, 0.0, 0.0],
        "q_Zone": ["Center", "Left", "Back", "Back"],
        "q_Cross": [False, True, False, False],
        "q_Longball": [False, True, False, False],
        "q_Throughball": [False, False, False, False],
        "q_KeyPass": [True, False, False, False],
        "q_Chipped": [False, False, False, False],
        "q_HeadPass": [False, False, False, False],
        "q_ThrowIn": [False, False, False, False],
        "q_CornerTaken": [False, False, False, False],
        "q_FreekickTaken": [False, False, False, False],
        "q_LayOff": [False, False, False, False],
        "q_IntentionalAssist": [False, False, False, False],
        # Always false on passes in the real data, so it must not be loaded.
        "q_Assisted": [False, False, False, False],
        # A column we never asked for: extraction must not carry it through.
        "q_SomethingElse": [1, 2, 3, 4],
    }
    return pd.DataFrame(base)


def test_extract_passes_keeps_only_pass_events() -> None:
    out = ex.extract_passes(_events())
    assert len(out) == 2
    assert set(out["event_id"]) == {10, 11}


def test_extract_passes_renames_qualifiers_to_readable_names() -> None:
    """`q_Cross` means nothing to an LLM; `is_cross` does. See D-009."""
    out = ex.extract_passes(_events())
    assert "is_cross" in out.columns
    assert "is_long_ball" in out.columns
    assert "pass_length" in out.columns
    assert "pass_angle" in out.columns
    # No source-shaped names survive.
    assert not [c for c in out.columns if c.startswith("q_")]
    assert out.loc[out["event_id"] == 11, "is_cross"].item()
    assert not out.loc[out["event_id"] == 10, "is_cross"].item()


def test_extract_passes_derives_is_completed_from_outcome() -> None:
    out = ex.extract_passes(_events()).set_index("event_id")
    assert out.loc[10, "is_completed"]
    assert not out.loc[11, "is_completed"]


def test_extract_passes_drops_unused_and_unknown_columns() -> None:
    out = ex.extract_passes(_events())
    assert "q_Assisted" not in out.columns
    assert "is_assisted" not in out.columns
    assert "q_SomethingElse" not in out.columns
    assert "type" not in out.columns


def test_extract_passes_emits_exactly_the_table_columns_in_order() -> None:
    """The loader COPYs positionally, so column order is part of the contract."""
    out = ex.extract_passes(_events())
    assert tuple(out.columns) == ex.TABLE_COLUMNS["passes"]


# ---------------------------------------------------------------------------
# matches
# ---------------------------------------------------------------------------


def _matches() -> pd.DataFrame:
    row = dict.fromkeys(ex.TABLE_COLUMNS["matches"], None)
    frame = pd.DataFrame([row, row]).astype("object")
    frame["match_id"] = [1, 2]
    frame["comp"] = ["eng", "eng"]
    frame["season"] = ["2526", "2526"]
    frame["date"] = pd.to_datetime(["2025-08-15", "2025-08-16"])
    frame["home_team_id"] = [100, 200]
    frame["away_team_id"] = [200, 100]
    frame["kickoff"] = ["2025-08-15T20:00:00", None]
    # Nullable boolean in the source.
    frame["score_matches_events"] = pd.array([True, None], dtype="boolean")
    return frame


def test_extract_matches_resolves_null_score_flag_to_true() -> None:
    """Day 1 rule: score_matches_events is nullable and null means 'no mismatch'."""
    out = ex.extract_matches(_matches()).set_index("match_id")
    assert out.loc[1, "score_matches_events"]
    assert out.loc[2, "score_matches_events"]
    assert out["score_matches_events"].isna().sum() == 0


def test_extract_matches_parses_kickoff_to_timestamp() -> None:
    out = ex.extract_matches(_matches()).set_index("match_id")
    assert isinstance(out.loc[1, "kickoff"], pd.Timestamp)
    assert pd.isna(out.loc[2, "kickoff"])


def test_extract_matches_emits_table_columns() -> None:
    out = ex.extract_matches(_matches())
    assert tuple(out.columns) == ex.TABLE_COLUMNS["matches"]


# ---------------------------------------------------------------------------
# dimension filtering
# ---------------------------------------------------------------------------


def test_referenced_ids_unions_every_id_column_including_assists() -> None:
    """A player referenced only as an assister still needs a players row,
    otherwise the shots.assist_player_id foreign key fails."""
    pms = pd.DataFrame({"player_id": [1], "team_id": [10], "opponent_id": [20]})
    lineups = pd.DataFrame({"player_id": [2], "team_id": [10], "opponent_id": [20]})
    shots = pd.DataFrame(
        {"player_id": [3], "assist_player_id": [4], "team_id": [30], "opponent_id": [40]}
    )
    passes = pd.DataFrame({"player_id": [5], "team_id": [50]})
    matches = pd.DataFrame({"home_team_id": [60], "away_team_id": [70]})

    players = ex.referenced_player_ids([pms, lineups, shots, passes])
    teams = ex.referenced_team_ids([pms, lineups, shots, passes, matches])

    assert players == {1, 2, 3, 4, 5}
    assert teams == {10, 20, 30, 40, 50, 60, 70}


def test_referenced_ids_ignore_nulls() -> None:
    frame = pd.DataFrame({"player_id": pd.array([1, None, 3], dtype="Int32")})
    assert ex.referenced_player_ids([frame]) == {1, 3}


def test_extract_teams_filters_to_referenced_ids() -> None:
    teams = pd.DataFrame(
        {
            "team_id": [10, 20, 30],
            "team": ["A", "B", "C"],
            "country": ["x", "y", "z"],
            "team_type": ["club"] * 3,
            "n_matches": [1, 2, 3],
        }
    )
    out = ex.extract_teams(teams, {10, 30})
    assert list(out["team_id"]) == [10, 30]
    assert tuple(out.columns) == ex.TABLE_COLUMNS["teams"]


def test_extract_players_filters_and_projects() -> None:
    players = pd.DataFrame(
        {
            "player_id": [1, 2],
            "player": ["P1", "P2"],
            "height_cm": [180, 190],
            "weight_kg": [75, 80],
            "birth_year_est": [1998, 1999],
            "main_position": ["DC", "FW"],
            "n_appearances": [10, 20],
        }
    )
    out = ex.extract_players(players, {2})
    assert list(out["player_id"]) == [2]
    assert tuple(out.columns) == ex.TABLE_COLUMNS["players"]


def test_extract_teams_raises_when_a_referenced_id_is_missing() -> None:
    """Better to fail in Python with a clear message than to hit a foreign key
    violation 1.08M rows into a COPY."""
    teams = pd.DataFrame({"team_id": [10], "team": ["A"], "country": ["x"], "team_type": ["club"]})
    with pytest.raises(ValueError, match="99"):
        ex.extract_teams(teams, {10, 99})


# ---------------------------------------------------------------------------
# player_match_stats / shots / lineups projections
# ---------------------------------------------------------------------------


def test_extract_player_match_stats_drops_vacuous_in_lineup_column() -> None:
    """`in_lineup` is true for every source row (day 1 finding), so it carries
    no information and is not loaded."""
    row = dict.fromkeys(ex.TABLE_COLUMNS["player_match_stats"], 0)
    frame = pd.DataFrame([row])
    frame["in_lineup"] = True
    out = ex.extract_player_match_stats(frame)
    assert "in_lineup" not in out.columns
    assert tuple(out.columns) == ex.TABLE_COLUMNS["player_match_stats"]


def test_extract_shots_emits_table_columns() -> None:
    row = dict.fromkeys(ex.TABLE_COLUMNS["shots"], 0)
    frame = pd.DataFrame([row])
    frame["player"] = "name-to-drop"
    out = ex.extract_shots(frame)
    assert "player" not in out.columns
    assert tuple(out.columns) == ex.TABLE_COLUMNS["shots"]


def test_extract_lineups_emits_table_columns() -> None:
    row = dict.fromkeys(ex.TABLE_COLUMNS["lineups"], 0)
    frame = pd.DataFrame([row])
    frame["height_cm"] = 180
    out = ex.extract_lineups(frame)
    assert "height_cm" not in out.columns
    assert tuple(out.columns) == ex.TABLE_COLUMNS["lineups"]


# ---------------------------------------------------------------------------
# data quality report -> rows
# ---------------------------------------------------------------------------


def _report() -> dict:
    return {
        "results": {
            "eng": {
                "league": "Premier League",
                "metrics": {"match_coverage_pct": 100.0, "coords_out_of_range": 0},
                "status": {"match_coverage_pct": "pass", "coords_out_of_range": "pass"},
                "info": {},
                "gaps": [],
                "issues": [],
            },
            "esp": {
                "league": "La Liga",
                "metrics": {"match_coverage_pct": 97.0, "coords_out_of_range": 4},
                "status": {"match_coverage_pct": "degraded", "coords_out_of_range": "degraded"},
                "info": {},
                "gaps": [],
                "issues": [],
            },
        },
        "feature_flags": {"per-90": "degraded", "xG analizi": "pass"},
    }


def test_data_quality_rows_are_tidy_one_row_per_comp_and_metric() -> None:
    metrics, _ = ex.extract_data_quality(_report(), data_tag="data-v0.1.0")
    assert len(metrics) == 4
    assert tuple(metrics.columns) == ex.TABLE_COLUMNS["data_quality"]
    eng_cov = metrics[(metrics["comp"] == "eng") & (metrics["metric"] == "match_coverage_pct")]
    assert eng_cov["value"].item() == 100.0
    assert eng_cov["status"].item() == "pass"
    assert eng_cov["target"].item() == 99.0
    assert eng_cov["critical_floor"].item() == 95.0
    # A non-critical metric has no floor.
    no_floor = metrics[metrics["metric"] == "coords_out_of_range"]["critical_floor"]
    assert no_floor.isna().all()


def test_data_quality_features_carry_run_metadata() -> None:
    _, features = ex.extract_data_quality(_report(), data_tag="data-v0.1.0")
    assert tuple(features.columns) == ex.TABLE_COLUMNS["data_quality_features"]
    assert len(features) == 2
    assert set(features["data_tag"]) == {"data-v0.1.0"}
    assert (features["run_at"] == features["run_at"].iloc[0]).all()


def test_data_quality_run_at_is_shared_between_both_frames() -> None:
    metrics, features = ex.extract_data_quality(_report(), data_tag="t")
    assert metrics["run_at"].iloc[0] == features["run_at"].iloc[0]
