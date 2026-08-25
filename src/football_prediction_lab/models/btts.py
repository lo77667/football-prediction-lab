"""Probabilistic BTTS model and time-ordered evaluation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football_prediction_lab.features.pre_match import FEATURE_COLUMNS

LEGACY_FEATURE_COLUMNS = [
    "home_avg_scored_5",
    "home_avg_conceded_5",
    "home_btts_rate_5",
    "away_avg_scored_5",
    "away_avg_conceded_5",
    "away_btts_rate_5",
    "home_matches_before",
    "away_matches_before",
]


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def temporal_split(
    frame: pd.DataFrame,
    *,
    train_fraction: float = 0.7,
    validation_fraction: float = 0.15,
) -> TemporalSplit:
    """Split an already point-in-time ordered frame without shuffling."""

    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must be below 1")

    ordered = frame.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    train_end = int(len(ordered) * train_fraction)
    validation_end = train_end + int(len(ordered) * validation_fraction)
    if train_end < 1 or validation_end <= train_end or validation_end >= len(ordered):
        raise ValueError("frame is too small for the requested temporal split")
    return TemporalSplit(
        train=ordered.iloc[:train_end].copy(),
        validation=ordered.iloc[train_end:validation_end].copy(),
        test=ordered.iloc[validation_end:].copy(),
    )


class BttsLogisticBaseline:
    """A reproducible probabilistic baseline for the BTTS market."""

    model_version = "btts-logistic-v0.2"
    feature_version = "pre-match-rolling-v0.2"

    def __init__(
        self,
        *,
        random_state: int = 42,
        feature_columns: Sequence[str] | None = None,
    ) -> None:
        self.feature_columns = list(feature_columns or FEATURE_COLUMNS)
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

    def fit(self, frame: pd.DataFrame) -> BttsLogisticBaseline:
        _validate_training_frame(frame, self.feature_columns)
        self.pipeline.fit(frame[self.feature_columns], frame["btts"])
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        _validate_feature_frame(frame, self.feature_columns)
        probabilities = self.pipeline.predict_proba(frame[self.feature_columns])[:, 1]
        return pd.Series(probabilities, index=frame.index, name="probability_yes")


def _validate_training_frame(frame: pd.DataFrame, feature_columns: Sequence[str]) -> None:
    _validate_feature_frame(frame, feature_columns)
    if "btts" not in frame.columns:
        raise ValueError("training frame requires btts target")
    if frame["btts"].nunique() < 2:
        raise ValueError("training target must contain both BTTS classes")


def _validate_feature_frame(frame: pd.DataFrame, feature_columns: Sequence[str]) -> None:
    missing = set(feature_columns).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing model features: {sorted(missing)}")
