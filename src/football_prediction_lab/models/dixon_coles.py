"""Leakage-safe Dixon-Coles correction over pre-match expected goals."""

from __future__ import annotations

from dataclasses import dataclass
from math import factorial

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DixonColesConfig:
    """Bounded grid used to estimate low-score dependence."""

    rho_min: float = -0.25
    rho_max: float = 0.25
    rho_step: float = 0.01
    max_goals: int = 10


class DixonColesBTTS:
    """Apply the Dixon-Coles low-score correction to pre-match goal rates.

    The rates must be created from point-in-time features. Observed goals are
    accepted only by ``fit`` as labels and never by ``predict_probability``.
    """

    def __init__(self, config: DixonColesConfig | None = None) -> None:
        self.config = config or DixonColesConfig()
        if self.config.rho_min >= self.config.rho_max or self.config.rho_step <= 0:
            raise ValueError("invalid rho grid")
        if self.config.max_goals < 2:
            raise ValueError("max_goals must be at least 2")
        self.rho = 0.0
        self._fitted = False

    def fit(self, frame: pd.DataFrame) -> DixonColesBTTS:
        self._validate(frame, require_labels=True)
        home = frame["lambda_home"].to_numpy(float)
        away = frame["lambda_away"].to_numpy(float)
        home_goals = frame["home_goals"].to_numpy(int)
        away_goals = frame["away_goals"].to_numpy(int)
        candidates = np.arange(
            self.config.rho_min,
            self.config.rho_max + self.config.rho_step / 2,
            self.config.rho_step,
        )
        scores = [
            self._log_likelihood(home, away, home_goals, away_goals, float(rho))
            for rho in candidates
        ]
        self.rho = float(candidates[int(np.argmax(scores))])
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        self._validate(frame, require_labels=False)
        probabilities = [
            1.0
            - self._score_probability(float(home), float(away)).get((0, 0), 0.0)
            - self._score_probability(float(home), float(away)).get((1, 0), 0.0)
            - self._score_probability(float(home), float(away)).get((0, 1), 0.0)
            for home, away in zip(frame["lambda_home"], frame["lambda_away"])
        ]
        return pd.Series(
            np.clip(probabilities, 0.0, 1.0), index=frame.index, name="probability_yes"
        )

    def _log_likelihood(
        self,
        home: np.ndarray,
        away: np.ndarray,
        home_goals: np.ndarray,
        away_goals: np.ndarray,
        rho: float,
    ) -> float:
        total = 0.0
        for lh, la, hg, ag in zip(home, away, home_goals, away_goals):
            probabilities = self._score_probability(lh, la, rho)
            total += np.log(max(probabilities.get((int(hg), int(ag)), 1e-15), 1e-15))
        return float(total)

    def _score_probability(
        self, lambda_home: float, lambda_away: float, rho: float | None = None
    ) -> dict[tuple[int, int], float]:
        rho = self.rho if rho is None else rho
        scores: dict[tuple[int, int], float] = {}
        for home_goals in range(self.config.max_goals + 1):
            for away_goals in range(self.config.max_goals + 1):
                value = np.exp(-(lambda_home + lambda_away))
                value *= lambda_home**home_goals / factorial(home_goals)
                value *= lambda_away**away_goals / factorial(away_goals)
                value *= self._tau(home_goals, away_goals, lambda_home, lambda_away, rho)
                scores[(home_goals, away_goals)] = max(float(value), 0.0)
        normalizer = sum(scores.values())
        return {key: value / normalizer for key, value in scores.items()}

    @staticmethod
    def _tau(
        home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float
    ) -> float:
        if home_goals == 0 and away_goals == 0:
            return 1.0 - lambda_home * lambda_away * rho
        if home_goals == 0 and away_goals == 1:
            return 1.0 + lambda_home * rho
        if home_goals == 1 and away_goals == 0:
            return 1.0 + lambda_away * rho
        if home_goals == 1 and away_goals == 1:
            return 1.0 - rho
        return 1.0

    @staticmethod
    def _validate(frame: pd.DataFrame, *, require_labels: bool) -> None:
        required = {"lambda_home", "lambda_away"}
        if require_labels:
            required |= {"home_goals", "away_goals"}
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"missing Dixon-Coles columns: {missing}")
        values = frame[list(required)].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
            raise ValueError("Dixon-Coles values must be finite")
        if (values[["lambda_home", "lambda_away"]] <= 0).any().any():
            raise ValueError("expected goals must be positive")


__all__ = ["DixonColesBTTS", "DixonColesConfig"]
