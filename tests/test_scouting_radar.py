"""plot_radar(): pure plotting, no DB — built from a hand-built PlayerProfile."""

from __future__ import annotations

from datetime import UTC, datetime

from football_ai.scouting.profile import CategoryScore, PlayerProfile
from football_ai.scouting.radar import plot_radar


def _profile(categories, radar_categories):
    return PlayerProfile(
        player_id=1,
        player="Test Player",
        teams="Test FC",
        comp="Premier League",
        season="2025/26",
        position_group="FW",
        position_group_broad="ATT",
        position_source="starts",
        position_share=1.0,
        minutes_played=1200,
        matches=14,
        min_minutes_threshold=900,
        sample_warning=None,
        avg_opponent_possession_pct=55.0,
        possession_adjustment_note=None,
        radar_categories=radar_categories,
        categories=categories,
        generated_at=datetime.now(UTC),
    )


def test_plot_radar_matches_category_count():
    categories = [
        CategoryScore(category="shooting", score=70.0, metrics=[]),
        CategoryScore(category="creation", score=40.0, metrics=[]),
        CategoryScore(category="duels", score=55.0, metrics=[]),
    ]
    fig = plot_radar(_profile(categories, ["shooting", "creation", "duels"]))
    assert fig is not None


def test_plot_radar_handles_null_category_score():
    categories = [
        CategoryScore(category="shooting", score=None, metrics=[]),
        CategoryScore(category="creation", score=40.0, metrics=[]),
        CategoryScore(category="duels", score=55.0, metrics=[]),
    ]
    fig = plot_radar(_profile(categories, ["shooting", "creation", "duels"]))
    assert fig is not None


def test_plot_radar_handles_gk_three_axis_profile():
    categories = [
        CategoryScore(category="goalkeeping", score=65.0, metrics=[]),
        CategoryScore(category="passing", score=50.0, metrics=[]),
        CategoryScore(category="duels", score=30.0, metrics=[]),
    ]
    fig = plot_radar(_profile(categories, ["goalkeeping", "passing", "duels"]))
    assert fig is not None
