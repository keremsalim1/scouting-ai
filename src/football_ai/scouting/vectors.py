"""Pure vector math for similarity: z-scoring, role weights, PCA.

No DB, no I/O — kept separate from the build script so the arithmetic is
testable without a database, the same split as Day 7's ``calc.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.decomposition import PCA

from football_ai.metrics import MetricsConfig

VECTOR_WIDTH = 35


def zscore_columns(matrix: np.ndarray) -> np.ndarray:
    """Column-wise z-score. Zero-variance columns become zeros, never NaN.

    The guard is applied *before* dividing rather than cleaning up after: a
    zero-variance column divides 0 by 0, and `inf * 0` would escape a
    post-hoc `nan_to_num` as a silent wrong number rather than a loud one.
    A zero-variance column carries no information, so zero is the honest
    value — every player sits exactly at the group mean.
    """
    matrix = np.asarray(matrix, dtype=float)
    mean = matrix.mean(axis=0)
    # ddof=0: the population standard deviation. The cell *is* the population
    # here - every qualified player in it - not a sample drawn from one.
    stddev = matrix.std(axis=0, ddof=0)
    usable = stddev > 0
    out = np.zeros_like(matrix)
    out[:, usable] = (matrix[:, usable] - mean[usable]) / stddev[usable]
    return out


def role_scale_factors(metric_keys: Sequence[str], config: MetricsConfig) -> np.ndarray:
    """Per-dimension multipliers that give every category equal total weight.

    Scaling a dimension by ``w`` before a cosine gives it effective weight
    ``w**2`` in the inner product, so the multiplier is the square root of the
    intended weight ``1 / (C * k_c)`` — C categories, k_c metrics in this
    metric's category. Using the weight directly would square it and let a
    small category quietly dominate.
    """
    by_key = {m.key: m for m in config.metrics}
    categories = [by_key[key].category for key in metric_keys]
    counts: dict[str, int] = {}
    for category in categories:
        counts[category] = counts.get(category, 0) + 1
    n_categories = len(counts)
    return np.array(
        [np.sqrt(1.0 / (n_categories * counts[category])) for category in categories],
        dtype=float,
    )


def fit_pca(
    matrix: np.ndarray, variance_target: float = 0.90, random_state: int = 0
) -> tuple[np.ndarray, int]:
    """Project onto the fewest components explaining ``variance_target``.

    Component signs are arbitrary in a PCA fit and can flip between runs,
    which would churn every stored vector on an unchanged rebuild. Each
    component is therefore sign-normalised: if its largest-magnitude loading
    is negative, the component and its projection are negated. That is what
    lets the build stay deterministic and the components go unstored.
    """
    matrix = np.asarray(matrix, dtype=float)
    full = PCA(random_state=random_state).fit(matrix)
    cumulative = np.cumsum(full.explained_variance_ratio_)
    n_components = int(np.searchsorted(cumulative, variance_target) + 1)
    n_components = min(n_components, matrix.shape[1])

    components = full.components_[:n_components]
    projection = (matrix - full.mean_) @ components.T

    dominant = np.argmax(np.abs(components), axis=1)
    flip = np.sign(components[np.arange(n_components), dominant])
    flip[flip == 0] = 1.0
    return projection * flip, n_components


def pad_to(vector: np.ndarray, width: int = VECTOR_WIDTH) -> np.ndarray:
    """Right-pad with zeros to the fixed pgvector column width.

    Safe because every comparison happens inside one broad group, where all
    rows share the same padding: the trailing zeros contribute identically to
    both sides of every cosine and change no ranking.
    """
    vector = np.asarray(vector, dtype=float)
    out = np.zeros(width, dtype=float)
    out[: vector.shape[0]] = vector
    return out
