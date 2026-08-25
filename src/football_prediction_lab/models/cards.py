"""Baseline probabilistic model for total yellow cards over 3.5."""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS


class TotalYellowCardsBaseline:
    """A separate model for the total-yellow-cards-over-3.5 market."""

    model_version = "cards-logistic-v0.1"
    feature_version = "card-rolling-v0.1"

    def __init__(self, *, random_state: int = 42) -> None:
        self.pipeline = Pipeline(
            steps=[
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=1_000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        )
        self._fitted = False

    def fit(self, frame: pd.DataFrame) -> TotalYellowCardsBaseline:
        _validate_frame(frame)
        self.pipeline.fit(frame[CARD_FEATURE_COLUMNS], frame["total_yellows_over_3_5"])
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        missing = set(CARD_FEATURE_COLUMNS).difference(frame.columns)
        if missing:
            raise ValueError(f"Missing card features: {sorted(missing)}")
        values = self.pipeline.predict_proba(frame[CARD_FEATURE_COLUMNS])[:, 1]
        return pd.Series(values, index=frame.index, name="probability_yes")


def _validate_frame(frame: pd.DataFrame) -> None:
    missing = set(CARD_FEATURE_COLUMNS).difference(frame.columns)
    if "total_yellows_over_3_5" not in frame.columns:
        missing.add("total_yellows_over_3_5")
    if missing:
        raise ValueError(f"Missing card model columns: {sorted(missing)}")
    if frame["total_yellows_over_3_5"].nunique() < 2:
        raise ValueError("card target must contain both classes")
