"""Unit tests for the Day 1 OpenPlay validation logic.

Tests that only exercise pure functions (`check`, `feature_flags`) run always.
Tests that touch the real OpenPlay dataset are marked `data` and skipped by
default, because they need a multi-megabyte download.
"""

from __future__ import annotations

import pytest
import validate_openplay as v

# ---------------------------------------------------------------------------
# check(): threshold -> pass / degraded / disabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        # Higher-is-better, non-critical target met.
        ("match_coverage_pct", 100.0, "pass"),
        # Exactly on target counts as pass (comparison is >=).
        ("match_coverage_pct", 99.0, "pass"),
        # Below target but above the critical floor (95.0).
        ("match_coverage_pct", 97.0, "degraded"),
        # Exactly on the critical floor is still degraded (comparison is <).
        ("match_coverage_pct", 95.0, "degraded"),
        # Below the critical floor disables the dependent features.
        ("match_coverage_pct", 94.9, "disabled"),
        ("shot_xg_filled_pct", 99.0, "pass"),
        ("shot_xg_filled_pct", 95.0, "degraded"),
        ("shot_xg_filled_pct", 90.0, "degraded"),
        ("shot_xg_filled_pct", 89.9, "disabled"),
        ("pass_end_xy_filled_pct", 100.0, "pass"),
        ("pass_end_xy_filled_pct", 50.0, "disabled"),
    ],
)
def test_check_higher_is_better(name: str, value: float, expected: str) -> None:
    assert v.check(name, value) == expected


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        # Lower-is-better: 0 out-of-range coordinates is the target.
        ("coords_out_of_range", 0, "pass"),
        ("coords_out_of_range", 1, "degraded"),
        ("coords_out_of_range", 100_000, "degraded"),
        ("score_mismatch_pct", 0.0, "pass"),
        ("score_mismatch_pct", 1.0, "pass"),
        ("score_mismatch_pct", 1.1, "degraded"),
        ("unknown_minutes_pct", 0.5, "pass"),
        ("unknown_minutes_pct", 42.0, "degraded"),
    ],
)
def test_check_lower_is_better(name: str, value: float, expected: str) -> None:
    assert v.check(name, value) == expected


def test_lower_is_better_metrics_are_never_disabled() -> None:
    """No lower-is-better metric is critical, so it can only degrade.

    This pins the current policy: only xG fill, pass-coordinate fill and match
    coverage can switch a feature off entirely.
    """
    for name in v.LOWER_IS_BETTER:
        assert name not in v.CRITICAL
        assert v.check(name, 10_000) == "degraded"


def test_every_target_has_affected_features() -> None:
    """A metric with no AFFECTS entry would raise a KeyError in feature_flags."""
    assert set(v.TARGETS) == set(v.AFFECTS)


def test_critical_floors_are_below_their_targets() -> None:
    for name, floor in v.CRITICAL.items():
        assert floor < v.TARGETS[name]


# ---------------------------------------------------------------------------
# feature_flags(): worst status across leagues wins
# ---------------------------------------------------------------------------


def _results(**per_league: dict[str, str]) -> dict:
    """Build a minimal results dict: league -> {"status": {metric: status}}.

    Metrics not named default to "pass" so each test only states what differs.
    """
    out = {}
    for league, overrides in per_league.items():
        status = dict.fromkeys(v.TARGETS, "pass")
        status.update(overrides)
        out[league] = {"status": status}
    return out


def test_feature_flags_all_pass() -> None:
    flags = v.feature_flags(_results(eng={}, esp={}, ita={}))
    assert set(flags.values()) == {"pass"}
    # Every feature named in AFFECTS must appear.
    expected = {f for features in v.AFFECTS.values() for f in features}
    assert set(flags) == expected


def test_feature_flags_disabled_in_one_league_disables_feature() -> None:
    """A single league failing a critical threshold switches the feature off."""
    flags = v.feature_flags(_results(eng={}, esp={"shot_xg_filled_pct": "disabled"}, ita={}))
    for feature in v.AFFECTS["shot_xg_filled_pct"]:
        assert flags[feature] == "disabled"
    # Unrelated features are untouched.
    assert flags["pas haritaları"] == "pass"


def test_feature_flags_takes_the_worst_status() -> None:
    flags = v.feature_flags(
        _results(
            eng={"match_coverage_pct": "degraded"},
            esp={"match_coverage_pct": "disabled"},
            ita={},
        )
    )
    for feature in v.AFFECTS["match_coverage_pct"]:
        assert flags[feature] == "disabled"


def test_feature_flags_degraded_does_not_override_disabled() -> None:
    """Order of leagues must not matter: disabled first, degraded second."""
    flags = v.feature_flags(
        _results(
            eng={"shot_xg_filled_pct": "disabled"},
            esp={"shot_xg_filled_pct": "degraded"},
        )
    )
    assert flags["xG analizi"] == "disabled"


def test_feature_flags_is_sorted() -> None:
    flags = v.feature_flags(_results(eng={}))
    assert list(flags) == sorted(flags)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_to_markdown_reports_empty_gap_sections() -> None:
    results = {
        comp: {
            "league": name,
            "metrics": dict.fromkeys(v.TARGETS, 100.0),
            "status": dict.fromkeys(v.TARGETS, "pass"),
            "info": {"matches": 380},
            "gaps": [],
            "issues": [],
        }
        for comp, name in v.LEAGUES.items()
    }
    md = v.to_markdown(results, v.feature_flags(results))
    assert md.startswith(f"# OpenPlay {v.SEASON} veri doğrulama raporu")
    assert md.count("Eksik veya sorunlu maç yok.") == len(v.LEAGUES)
    for name in v.LEAGUES.values():
        assert f"## {name}: eksik ve sorunlu maçlar" in md


# ---------------------------------------------------------------------------
# Real-data tests (opt-in: pytest -m data)
# ---------------------------------------------------------------------------


@pytest.mark.data
def test_season_code_matches_claimed_encoding() -> None:
    import openplay as op

    assert op.normalize_season(v.SEASON) == v.SEASON_CODE


@pytest.mark.data
@pytest.mark.parametrize("comp", list(v.LEAGUES))
def test_validate_real_league_is_fully_covered(comp: str) -> None:
    import warnings

    import openplay as op

    warnings.simplefilter("ignore", op.CoverageWarning)
    result = v.validate(comp)
    assert result["info"]["matches"] == v.EXPECTED_MATCHES
    assert result["metrics"]["match_coverage_pct"] == 100.0
    assert result["status"] == dict.fromkeys(v.TARGETS, "pass"), result["metrics"]
