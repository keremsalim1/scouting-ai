"""Which metrics.yaml categories a radar shows for each position group.

`discipline` is never included: it penalizes a player for cards, which is
not a scouting-relevant skill axis. The mapping itself is a football-logic
default (see docs/superpowers/specs/2026-11-18-day7-player-profile-design.md),
not derived from data, so it lives here as a plain constant rather than in
config/metrics.yaml, which is validated against the actual metric set.
"""

from __future__ import annotations

POSITION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "GK": ("goalkeeping", "passing"),
    "CB": ("defending", "duels", "passing", "progression"),
    "FB": ("defending", "duels", "passing", "progression", "creation"),
    "DM": ("defending", "duels", "passing", "progression"),
    "CM": ("passing", "progression", "creation", "defending"),
    "AM": ("creation", "passing", "shooting", "progression"),
    "W": ("creation", "shooting", "duels", "progression"),
    "FW": ("shooting", "creation", "duels"),
}
