"""Vector math for similarity: pure, no DB."""

from __future__ import annotations

import numpy as np

from football_ai.metrics import load
from football_ai.scouting.broad_groups import broad_metric_keys
from football_ai.scouting.vectors import (
    fit_pca,
    pad_to,
    role_scale_factors,
    zscore_columns,
)


def test_zscore_centres_and_scales_each_column():
    out = zscore_columns(np.array([[1.0], [2.0], [3.0]]))
    assert out.mean() == 0.0
    assert np.allclose(out.ravel(), [-1.224744871, 0.0, 1.224744871])


def test_zero_variance_column_becomes_zeros_not_nan():
    out = zscore_columns(np.array([[5.0, 1.0], [5.0, 2.0], [5.0, 3.0]]))
    assert np.all(out[:, 0] == 0.0)
    assert not np.isnan(out).any()


def test_single_row_matrix_becomes_zeros_not_nan():
    out = zscore_columns(np.array([[7.0, 9.0]]))
    assert np.all(out == 0.0)


def test_role_scale_factors_square_to_the_specified_weight():
    # Effective weight inside a cosine inner product is the square of the
    # multiplier, so the multiplier must be sqrt(1 / (C * k_c)).
    config = load()
    keys = broad_metric_keys("ATT", config)
    by_key = {m.key: m for m in config.metrics}
    counts: dict[str, int] = {}
    for k in keys:
        counts[by_key[k].category] = counts.get(by_key[k].category, 0) + 1
    factors = role_scale_factors(keys, config)
    for factor, key in zip(factors, keys, strict=True):
        category = by_key[key].category
        assert np.isclose(factor**2, 1.0 / (len(counts) * counts[category]))


def test_role_weights_give_every_category_equal_total():
    config = load()
    keys = broad_metric_keys("ATT", config)
    by_key = {m.key: m for m in config.metrics}
    totals: dict[str, float] = {}
    for factor, key in zip(role_scale_factors(keys, config), keys, strict=True):
        totals.setdefault(by_key[key].category, 0.0)
        totals[by_key[key].category] += factor**2
    assert np.allclose(list(totals.values()), next(iter(totals.values())))


def test_fit_pca_keeps_enough_components_for_the_variance_target():
    rng = np.random.default_rng(0)
    matrix = zscore_columns(rng.normal(size=(200, 10)))
    projection, n_components = fit_pca(matrix, variance_target=0.90)
    assert projection.shape == (200, n_components)
    assert 1 <= n_components <= 10


def test_fit_pca_is_deterministic_across_runs():
    rng = np.random.default_rng(1)
    matrix = zscore_columns(rng.normal(size=(150, 8)))
    first, _ = fit_pca(matrix)
    second, _ = fit_pca(matrix)
    assert np.allclose(first, second)


def test_pad_to_appends_zeros_and_keeps_the_prefix():
    padded = pad_to(np.array([1.0, 2.0]), width=35)
    assert padded.shape == (35,)
    assert np.allclose(padded[:2], [1.0, 2.0])
    assert np.all(padded[2:] == 0.0)
