"""The similarity evaluation report: pure rendering, no DB."""

from __future__ import annotations

from eval_similarity import render


def _measured(headlines: dict[str, float], similarities: dict[str, float]) -> dict:
    groups = ("CB", "FB", "DM", "CM", "AM", "W", "FW")
    return {
        "base_rates": dict.fromkeys(groups, 0.5),
        "weightings": {
            weighting: {
                "scores": dict.fromkeys(groups, headline),
                "headline": headline,
                "mean_similarity": similarities[weighting],
                "confusion": {g: {g: 10} for g in groups},
                "sweep_seconds": 0.1,
            }
            for weighting, headline in headlines.items()
        },
    }


def test_winner_is_the_highest_position_consistency_not_the_highest_similarity():
    """A configuration that calls everyone similar has not discriminated, so
    mean similarity must never decide the winner."""
    report = render(
        _measured(
            headlines={"equal": 0.72, "role": 0.60, "pca": 0.61},
            similarities={"equal": 0.40, "role": 0.50, "pca": 0.99},
        )
    )
    assert "**Kazanan: `equal`**" in report
    assert "`pca`**" not in report


def test_report_does_not_claim_the_winner_won_on_mean_similarity():
    report = render(
        _measured(
            headlines={"equal": 0.600, "role": 0.601, "pca": 0.602},
            similarities={"equal": 0.40, "role": 0.50, "pca": 0.99},
        )
    )
    assert "ortalama benzerliği verdiği için seçildi" not in report


def test_a_high_mean_similarity_is_reported_as_a_caveat_not_a_credential():
    report = render(
        _measured(
            headlines={"equal": 0.600, "role": 0.601, "pca": 0.602},
            similarities={"equal": 0.40, "role": 0.50, "pca": 0.99},
        )
    )
    assert "ayırt" in report
