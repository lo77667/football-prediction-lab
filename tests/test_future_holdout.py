from football_prediction_lab.learning.future_holdout import is_future_holdout_available


def test_future_holdout_requires_observed_season_after_cutoff() -> None:
    assert (
        is_future_holdout_available(
            ["2324", "2425", "2526"],
            historical_through="2425",
            requested_future_season="2526",
        )
        is True
    )


def test_future_holdout_rejects_unobserved_season() -> None:
    assert (
        is_future_holdout_available(
            ["2324", "2425"],
            historical_through="2425",
            requested_future_season="2526",
        )
        is False
    )


def test_future_holdout_rejects_season_at_or_before_cutoff() -> None:
    observed = ["2324", "2425", "2526"]
    assert (
        is_future_holdout_available(
            observed,
            historical_through="2425",
            requested_future_season="2425",
        )
        is False
    )
