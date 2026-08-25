"""Leakage-safe statistical and odds benchmark helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_binary(values: pd.Series | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("historical targets must be finite and non-empty")
    if not np.isin(array, [0, 1]).all():
        raise ValueError("historical targets must be binary")
    return array


def constant_historical_rate(history_target: pd.Series | np.ndarray) -> float:
    """Return a probability using only targets observed in the supplied history."""

    return float(_validate_binary(history_target).mean())


def seasonal_historical_rate(
    frame: pd.DataFrame,
    target_column: str,
    season_column: str,
    test_season: str,
) -> float:
    """Return the rate from seasons strictly earlier than the requested test season."""

    if target_column not in frame or season_column not in frame:
        raise ValueError("target_column and season_column must exist")
    seasons = frame[season_column].astype(str)
    history = frame[seasons < str(test_season)]
    if history.empty:
        raise ValueError("no historical seasons precede test_season")
    return constant_historical_rate(history[target_column])


def last_n_historical_rate(history_target: pd.Series | np.ndarray, n: int) -> float:
    """Return the rate from the final n observations of an already time-ordered history."""

    if n < 1:
        raise ValueError("n must be positive")
    array = _validate_binary(history_target)
    return float(array[-n:].mean())


def decimal_odds_to_implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to an unadjusted implied probability."""

    odds = float(decimal_odds)
    if not np.isfinite(odds) or odds <= 1.0:
        raise ValueError("decimal odds must be finite and greater than 1")
    return 1.0 / odds


def remove_binary_overround(
    odds_a: float,
    odds_b: float,
) -> dict[str, float]:
    """Normalize two decimal-odds implied probabilities to sum to one."""

    implied_a = decimal_odds_to_implied_probability(odds_a)
    implied_b = decimal_odds_to_implied_probability(odds_b)
    overround = implied_a + implied_b
    return {
        "implied_a": implied_a,
        "implied_b": implied_b,
        "overround": overround,
        "fair_a": implied_a / overround,
        "fair_b": implied_b / overround,
    }


def theoretical_edge_and_ev(
    model_probability: float,
    decimal_odds: float,
    *,
    commission: float = 0.0,
) -> dict[str, float]:
    """Return descriptive, stake-free edge and theoretical expected value only."""

    probability = float(model_probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("model_probability must be within [0, 1]")
    if not 0.0 <= commission < 1.0:
        raise ValueError("commission must be within [0, 1)")
    odds = float(decimal_odds)
    implied = decimal_odds_to_implied_probability(odds)
    net_win_profit = (odds - 1.0) * (1.0 - commission)
    theoretical_ev = probability * net_win_profit - (1.0 - probability)
    return {
        "implied_probability": implied,
        "raw_edge": probability - implied,
        "theoretical_expected_value": theoretical_ev,
        "commission": commission,
    }
