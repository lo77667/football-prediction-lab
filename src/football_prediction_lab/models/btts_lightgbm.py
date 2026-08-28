"""LightGBM BTTS model wrapper.

Mirrors the BttsLogisticBaseline interface (fit, predict_probability).
Uses conservative defaults suitable for small/temporal sports datasets.
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

try:
    from lightgbm import LGBMClassifier
except Exception as exc:  # pragma: no cover - helpful error if dependency missing
    raise RuntimeError(
        "lightgbm is required for BttsLightGBMModel. Install with `pip install lightgbm`."
    ) from exc

from football_prediction_lab.data.schema import validate_pre_match_feature_columns
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import _validate_training_frame, _validate_feature_frame


class BttsLightGBMModel:
    """LightGBM-based probabilistic BTTS model.

    Defaults:
    - n_estimators=200
    - learning_rate=0.05
    - max_depth=6
    - subsample/colsample_bytree=0.8
    """

    model_version = "btts-lightgbm-v0.1"
    feature_version = "pre-match-rolling-v0.2"

    def __init__(
        self,
        *,
        random_state: int = 42,
        feature_columns: Sequence[str] | None = None,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        n_estimators: int = 200,
    ) -> None:
        if learning_rate <= 0 or max_depth < 1 or n_estimators < 1:
            raise ValueError("invalid hyperparameters")
        self.feature_columns = list(feature_columns or FEATURE_COLUMNS)
        validate_pre_match_feature_columns(self.feature_columns)
        self.model = LGBMClassifier(
            objective="binary",
            learning_rate=learning_rate,
            max_depth=max_depth,
            n_estimators=n_estimators,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=int(random_state),
        )
        self._fitted = False

    def fit(self, frame: pd.DataFrame) -> "BttsLightGBMModel":
        """Fit the LightGBM classifier on the provided training frame.

        The frame MUST contain the `btts` target and the model's feature columns.
        """
        _validate_training_frame(frame, self.feature_columns)
        X = frame[self.feature_columns]
        y = frame["btts"]
        try:
            # best-effort to address class imbalance
            self.model.set_params(class_weight="balanced")
        except Exception:
            pass
        self.model.fit(X, y)
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        """Return probability of BTTS == 1 for each row in `frame` as a pd.Series."""
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        _validate_feature_frame(frame, self.feature_columns)
        probabilities = self.model.predict_proba(frame[self.feature_columns])[:, 1]
        return pd.Series(probabilities, index=frame.index, name="probability_yes")
