"""Auditable Poisson goal-rate candidate for the BTTS market."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from football_prediction_lab.features.pre_match import FEATURE_COLUMNS

POISSON_BTTS_FEATURES = (
    "home_avg_scored_10",
    "away_avg_conceded_10",
    "away_avg_scored_10",
    "home_avg_conceded_10",
    "home_matches_before",
    "away_matches_before",
    "league_avg_goals_before",
)


@dataclass(frozen=True)
class PoissonBttsConfig:
    shrinkage_strength: float = 5.0
    max_lambda: float = 8.0
    feature_version: str = "pre-match-poisson-goals-v1"
    model_version: str = "poisson-goals-btts-v1"


class PoissonGoalsBtts:
    """Estimate two pre-match goal rates and derive P(BTTS)."""

    def __init__(self, config: PoissonBttsConfig | None = None) -> None:
        self.config = config or PoissonBttsConfig()
        if self.config.shrinkage_strength <= 0 or self.config.max_lambda <= 0:
            raise ValueError("Poisson configuration must be positive")
        self._fitted = False
        self._prior_goals_per_team = 0.75

    def fit(self, frame: pd.DataFrame) -> PoissonGoalsBtts:
        self._validate_features(frame)
        league_prior = pd.to_numeric(frame["league_avg_goals_before"], errors="coerce").dropna()
        if league_prior.empty:
            raise ValueError("training frame has no point-in-time league goal prior")
        self._prior_goals_per_team = float(
            np.clip(league_prior.mean() / 2.0, 1e-6, self.config.max_lambda)
        )
        self._fitted = True
        return self

    def predict_lambdas(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        self._validate_features(frame)
        home_raw = (
            frame["home_avg_scored_10"].astype(float) + frame["away_avg_conceded_10"].astype(float)
        ) / 2.0
        away_raw = (
            frame["away_avg_scored_10"].astype(float) + frame["home_avg_conceded_10"].astype(float)
        ) / 2.0
        home_weight = frame["home_matches_before"].astype(float).clip(lower=0, upper=10)
        away_weight = frame["away_matches_before"].astype(float).clip(lower=0, upper=10)
        home_weight = home_weight / (home_weight + self.config.shrinkage_strength)
        away_weight = away_weight / (away_weight + self.config.shrinkage_strength)
        home_lambda = self._shrink(home_raw, home_weight)
        away_lambda = self._shrink(away_raw, away_weight)
        return pd.DataFrame(
            {
                "lambda_home": home_lambda,
                "lambda_away": away_lambda,
            },
            index=frame.index,
        )

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        lambdas = self.predict_lambdas(frame)
        probability = (
            1.0
            - np.exp(-lambdas["lambda_home"])
            - np.exp(-lambdas["lambda_away"])
            + np.exp(-(lambdas["lambda_home"] + lambdas["lambda_away"]))
        )
        return probability.clip(0.0, 1.0).rename("probability_yes")

    def _shrink(self, raw: pd.Series, weight: pd.Series) -> pd.Series:
        value = weight * raw.astype(float) + (1.0 - weight) * self._prior_goals_per_team
        return value.clip(lower=1e-6, upper=self.config.max_lambda)

    @staticmethod
    def _validate_features(frame: pd.DataFrame) -> None:
        missing = set(POISSON_BTTS_FEATURES).difference(frame.columns)
        if missing:
            raise ValueError(f"Missing Poisson BTTS features: {sorted(missing)}")
        if set(POISSON_BTTS_FEATURES) - set(FEATURE_COLUMNS):
            raise ValueError("Poisson BTTS feature contract is not pre-match")
        values = frame[list(POISSON_BTTS_FEATURES)].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
            raise ValueError("Poisson BTTS features must be finite")
