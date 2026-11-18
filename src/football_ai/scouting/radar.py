"""Radar plot over a player's position-relevant categories.

Axis count comes entirely from `profile.radar_categories` — never hardcoded
— because it varies by position (GK: 2 categories, FB: 5).
"""

from __future__ import annotations

from matplotlib.figure import Figure
from mplsoccer import Radar

from football_ai.scouting.profile import PlayerProfile


def plot_radar(profile: PlayerProfile) -> Figure:
    scores_by_category = {cat.category: cat.score for cat in profile.categories}
    params = profile.radar_categories
    # A null category score (no qualifying metrics) plots as 0; the
    # underlying None is untouched on profile.categories for any other
    # consumer.
    values = [scores_by_category.get(category) or 0.0 for category in params]

    radar = Radar(params, min_range=[0] * len(params), max_range=[100] * len(params))
    fig, ax = radar.setup_axis()
    radar.draw_circles(ax=ax)
    radar.draw_radar(values, ax=ax)
    return fig
