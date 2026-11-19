"""Vector math for similarity: pure, no DB."""

from __future__ import annotations

import numpy as np

from football_ai.metrics import load
from football_ai.scouting.broad_groups import broad_metric_keys
from football_ai.scouting.vectors import (
    fit_pca,
    pad_to,
    role_scale_factors,
    sign_normalise,
    zscore_cell,
)


def _observed(matrix: np.ndarray) -> np.ndarray:
    """An all-observed imputation mask for `matrix`."""
    return np.zeros(matrix.shape, dtype=bool)


def test_zscore_centres_and_scales_each_column():
    matrix = np.array([[1.0], [2.0], [3.0]])
    out = zscore_cell(matrix, _observed(matrix))
    assert out.mean() == 0.0
    assert np.allclose(out.ravel(), [-1.224744871, 0.0, 1.224744871])


def test_zero_variance_column_becomes_zeros_not_nan():
    matrix = np.array([[5.0, 1.0], [5.0, 2.0], [5.0, 3.0]])
    out = zscore_cell(matrix, _observed(matrix))
    assert np.all(out[:, 0] == 0.0)
    assert not np.isnan(out).any()


def test_single_row_matrix_becomes_zeros_not_nan():
    matrix = np.array([[7.0, 9.0]])
    out = zscore_cell(matrix, _observed(matrix))
    assert np.all(out == 0.0)
    assert not np.isnan(out).any()


def test_all_imputed_column_becomes_zeros_not_nan():
    matrix = np.array([[1.0, 4.0], [1.0, 6.0], [1.0, 8.0]])
    imputed = np.array([[True, False], [True, False], [True, False]])
    out = zscore_cell(matrix, imputed)
    assert np.all(out[:, 0] == 0.0)
    assert not np.isnan(out).any()


def test_single_observed_value_in_a_column_becomes_zero_not_nan():
    matrix = np.array([[3.0], [99.0], [99.0]])
    imputed = np.array([[False], [True], [True]])
    out = zscore_cell(matrix, imputed)
    assert np.all(out == 0.0)
    assert not np.isnan(out).any()


def test_imputed_entries_are_held_out_of_the_mean_and_stddev():
    """An imputed entry means "we do not know", not "he did this much".

    Letting the fill value into the statistics would drag the distribution
    toward it and shift every observed player's score.
    """
    observed_only = np.array([[10.0], [20.0], [30.0]])
    out_clean = zscore_cell(observed_only, _observed(observed_only))

    with_filler = np.array([[10.0], [20.0], [30.0], [0.0], [0.0]])
    imputed = np.array([[False], [False], [False], [True], [True]])
    out_mixed = zscore_cell(with_filler, imputed)

    assert np.allclose(out_mixed[:3], out_clean)
    assert np.all(out_mixed[3:] == 0.0)


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


def test_sign_normalise_makes_the_dominant_loading_positive():
    components = np.array([[-0.9, 0.1], [0.2, -0.95]])
    out = sign_normalise(components)
    dominant = np.argmax(np.abs(out), axis=1)
    assert np.all(out[np.arange(len(out)), dominant] > 0)


def test_sign_normalise_leaves_an_already_positive_component_alone():
    components = np.array([[0.9, 0.1]])
    assert np.allclose(sign_normalise(components), components)


def test_sign_normalise_flips_the_whole_component_not_just_one_loading():
    components = np.array([[-0.9, 0.3]])
    assert np.allclose(sign_normalise(components), [[0.9, -0.3]])


def test_fit_pca_keeps_enough_components_for_the_variance_target():
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(200, 10))
    projection, n_components = fit_pca(matrix, variance_target=0.90)
    assert projection.shape == (200, n_components)
    assert 1 <= n_components <= 10


def test_fit_pca_projects_onto_sign_normalised_components():
    """The stored vector must not depend on which way the solver signed a
    component, or an unchanged rebuild would churn every row."""
    from sklearn.decomposition import PCA

    rng = np.random.default_rng(1)
    matrix = rng.normal(size=(150, 8))
    projection, n_components = fit_pca(matrix)

    raw = PCA(random_state=0).fit(matrix)
    components = sign_normalise(raw.components_[:n_components])
    expected = (matrix - raw.mean_) @ components.T
    assert np.allclose(projection, expected)


def test_pad_to_appends_zeros_and_keeps_the_prefix():
    padded = pad_to(np.array([1.0, 2.0]), width=35)
    assert padded.shape == (35,)
    assert np.allclose(padded[:2], [1.0, 2.0])
    assert np.all(padded[2:] == 0.0)
