"""Role descriptors: where a player operates, not how well.

Day 8's first measurement put position consistency at 68.9% against a 90%
target, and the midfield was the drag (DM 41.5%, CM 54.0%, AM 58.5%). The
first hypothesis — that Day 3's position labels are too noisy for ambiguous
midfielders — was tested and **refuted**: restricting the evaluation to
players with ``position_share >= 0.8`` moved the headline only 68.9% -> 70.5%,
and DM actually fell. The labels were not the ceiling.

The real gap is that all 38 metrics in ``config/metrics.yaml`` are volume or
rate measures, and none carries spatial information — while what separates a
DM from a CM from an AM *is* spatial. Measured on pass origin:

    DM  x=50.6 (sd 3.2)   CM  x=53.2 (sd 4.1)   AM  x=60.5 (sd 3.5)
    FW  |y-50|=24.6 (sd 4.5)                    W   |y-50|=32.1 (sd 3.2)

AM against CM on depth, and W against FW on width, are each roughly 1.9
standard deviations apart — a stronger separation than anything already in the
vector.

**Why these are not metrics.** ``metrics.yaml`` requires every entry to declare
``higher_is_better``, and its percentile layer guarantees "100 is always best in
the group". A pitch coordinate has no direction of merit: operating deep is not
better or worse than operating high, it is a different job. Forcing these into
that file would put a meaningless "positioning percentile" into every player
profile and a nonsense axis on every Day 7 radar. ``unit`` has no value that
fits a coordinate either.

So the similarity vector is deliberately *metrics + descriptors*: performance
measures from ``POSITION_CATEGORIES``, then this short, explicit list. This
amends the design doc's "no second list" constraint on purpose — that
constraint exists to stop a parallel *metric* set drifting from metrics.yaml,
and these are not metrics.
"""

from __future__ import annotations

from football_ai.metrics import MetricsConfig
from football_ai.scouting.broad_groups import broad_metric_keys

# Column names in football.player_action_position (migration 007), in vector
# dimension order. Appended after the performance metrics for every broad group,
# so a dimension index means the same thing within a group regardless of which
# descriptors exist.
ROLE_DESCRIPTORS: tuple[str, ...] = ("action_x", "action_lateral_dev")


def vector_feature_keys(broad: str, config: MetricsConfig) -> tuple[str, ...]:
    """Every dimension of a broad group's similarity vector, in order.

    This - not ``broad_metric_keys`` - is what gets stored in
    ``player_vectors.metric_keys`` and what the staleness check compares
    against, so the two cannot disagree about what a stored vector contains.
    """
    return (*broad_metric_keys(broad, config), *ROLE_DESCRIPTORS)
