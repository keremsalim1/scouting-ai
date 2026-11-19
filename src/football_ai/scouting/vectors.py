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


def zscore_cell(values: np.ndarray, imputed: np.ndarray) -> np.ndarray:
    """Column-wise z-score of one cell, holding imputed entries out.

    An imputed entry means "we do not know", not "the player did zero of it".
    Letting a run of them into the mean and standard deviation would drag the
    distribution toward the fill value and shift every observed player's score,
    so they are excluded from the statistics and left at 0 — the cell mean by
    construction.

    Three degenerate columns all resolve to zeros rather than NaN, and the
    guard is applied *before* dividing rather than cleaned up after: dividing
    first would produce `inf * 0`, which escapes a post-hoc `nan_to_num` as a
    silently wrong number instead of a loud one.

      * every entry imputed      - nothing observed to rank against
      * one observed value       - a population of one has no spread
      * zero standard deviation  - the column carries no information

    ``ddof=0`` throughout: the cell *is* the population (every qualified player
    in it), not a sample drawn from one.
    """
    values = np.asarray(values, dtype=float)
    imputed = np.asarray(imputed, dtype=bool)
    out = np.zeros_like(values)
    for column in range(values.shape[1]):
        observed = ~imputed[:, column]
        if not observed.any():
            continue
        column_values = values[observed, column]
        stddev = column_values.std(ddof=0)
        if stddev == 0:
            continue
        out[observed, column] = (column_values - column_values.mean()) / stddev
    return out


def sign_normalise(components: np.ndarray) -> np.ndarray:
    """Force each component's largest-magnitude loading positive.

    PCA component signs are arbitrary: the same data can yield ``+v`` or
    ``-v`` depending on solver, library version or platform. Storing an
    unnormalised projection would therefore churn every vector on a rebuild
    that changed nothing. Flipping the whole component (not just the dominant
    loading) preserves the basis and only fixes its orientation.
    """
    components = np.asarray(components, dtype=float)
    dominant = np.argmax(np.abs(components), axis=1)
    signs = np.sign(components[np.arange(components.shape[0]), dominant])
    signs[signs == 0] = 1.0
    return components * signs[:, None]


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
    # searchsorted(side='left') gives the first index where cumulative >=
    # target, so +1 is "the smallest count reaching the target". Clamped to the
    # components that actually exist: PCA returns min(n_samples, n_features) of
    # them, which is fewer than n_features for a cell with few players.
    n_components = int(np.searchsorted(cumulative, variance_target) + 1)
    n_components = min(n_components, len(full.components_))

    components = sign_normalise(full.components_[:n_components])
    return (matrix - full.mean_) @ components.T, n_components


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
