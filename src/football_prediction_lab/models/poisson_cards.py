"""Auditable Poisson card-rate candidate for the total-cards market."""

from __future__ import annotations

from dataclasses import dataclass
from math import factorial

import numpy as np
import pandas as pd

from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS

POISSON_CARDS_FEATURES = (
    "home_avg_yellows_10",
    "away_avg_yellows_10",
    "referee_avg_yellows_10",
    "home_card_matches_before",
    "away_card_matches_before",
)


@dataclass(frozen=True)
class PoissonCardsConfig:
    shrinkage_strength: float = 5.0
    referee_weight: float = 0.25
    max_lambda: float = 12.0
    feature_version: str = "pre-match-poisson-cards-v1"
    model_version: str = "poisson-cards-rate-v1"


class PoissonCardsRate:
    """Estimate a pre-match total-yellow-card rate and P(total > 3.5)."""

    def __init__(self, config: PoissonCardsConfig | None = None) -> None:
        self.config = config or PoissonCardsConfig()
        if self.config.shrinkage_strength <= 0 or self.config.max_lambda <= 0:
            raise ValueError("Poisson configuration must be positive")
        if not 0.0 <= self.config.referee_weight <= 1.0:
            raise ValueError("referee_weight must be between 0 and 1")
        self._fitted = False
        self._prior_total_cards = 3.5

    def fit(self, frame: pd.DataFrame) -> PoissonCardsRate:
        self._validate_features(frame)
        team_rate = frame["home_avg_yellows_10"].astype(float) + frame[
            "away_avg_yellows_10"
        ].astype(float)
        referee_rate = frame["referee_avg_yellows_10"].astype(float)
        combined = (
            1.0 - self.config.referee_weight
        ) * team_rate + self.config.referee_weight * referee_rate
        observed = combined.replace([np.inf, -np.inf], np.nan).dropna()
        if observed.empty:
            raise ValueError("training frame has no point-in-time card-rate prior")
        self._prior_total_cards = float(np.clip(observed.mean(), 1e-6, self.config.max_lambda))
        self._fitted = True
        return self

    def predict_lambda(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        self._validate_features(frame)
        team_rate = frame["home_avg_yellows_10"].astype(float) + frame[
            "away_avg_yellows_10"
        ].astype(float)
        referee_rate = frame["referee_avg_yellows_10"].astype(float)
        raw = (
            1.0 - self.config.referee_weight
        ) * team_rate + self.config.referee_weight * referee_rate
        team_matches = frame["home_card_matches_before"].astype(float) + frame[
            "away_card_matches_before"
        ].astype(float)
        evidence = team_matches.clip(lower=0)
        weight = evidence / (evidence + self.config.shrinkage_strength)
        value = weight * raw + (1.0 - weight) * self._prior_total_cards
        return value.clip(lower=1e-6, upper=self.config.max_lambda).rename("lambda_total_cards")

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        rate = self.predict_lambda(frame)
        cdf_at_three = sum(np.exp(-rate) * np.power(rate, k) / factorial(k) for k in range(4))
        return (1.0 - cdf_at_three).clip(0.0, 1.0).rename("probability_yes")

    @staticmethod
    def _validate_features(frame: pd.DataFrame) -> None:
        missing = set(POISSON_CARDS_FEATURES).difference(frame.columns)
        if missing:
            raise ValueError(f"Missing Poisson cards features: {sorted(missing)}")
        if set(POISSON_CARDS_FEATURES) - set(CARD_FEATURE_COLUMNS):
            raise ValueError("Poisson cards feature contract is not pre-match")
        values = frame[list(POISSON_CARDS_FEATURES)].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
            raise ValueError("Poisson cards features must be finite")
