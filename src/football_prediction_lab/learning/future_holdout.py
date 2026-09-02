"""Guards for evaluating a genuinely future holdout season."""

from __future__ import annotations


def is_future_holdout_available(
    observed_seasons: list[str],
    *,
    historical_through: str,
    requested_future_season: str,
) -> bool:
    """Return true only for an observed season beyond the frozen history cutoff."""

    return (
        requested_future_season in observed_seasons and requested_future_season > historical_through
    )
