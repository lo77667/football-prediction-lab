"""XGBoost BTTS model wrapper.

Implements the same interface as BttsLogisticBaseline:
- fit(frame) -> self
- predict_probability(frame) -> pd.Series

Type hints and docstrings follow project style. Uses conservative defaults to avoid
overfitting on small sports datasets.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

try:
    from xgboost import XGBClassifier
except Exception as exc:  # pragma: no cover - helpful error if dependency missing
    raise RuntimeError(
        "xgboost is required for BttsXGBoostModel. Install with `pip install xgboost`."
    ) from exc

from football_prediction_lab.data.schema import validate_pre_match_feature_columns
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import _validate_feature_frame, _validate_training_frame


class BttsXGBoostModel:
    """XGBoost-based probabilistic BTTS model.

    Conservatively tuned defaults:
    - learning_rate: 0.05
    - max_depth: 6
    - n_estimators: 100
    - subsample/colsample_bytree: 0.8
    """

    model_version = "btts-xgboost-v0.1"
    feature_version = "pre-match-rolling-v0.2"

    def __init__(
        self,
        *,
        random_state: int = 42,
        feature_columns: Sequence[str] | None = None,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        n_estimators: int = 100,
    ) -> None:
        if learning_rate <= 0 or max_depth < 1 or n_estimators < 1:
            raise ValueError("invalid hyperparameters")
        self.feature_columns = list(feature_columns or FEATURE_COLUMNS)
        validate_pre_match_feature_columns(self.feature_columns)
        self.random_state = int(random_state)
        self.model = XGBClassifier(
            objective="binary:logistic",
            use_label_encoder=False,
            eval_metric="logloss",
            learning_rate=learning_rate,
            max_depth=max_depth,
            n_estimators=n_estimators,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=self.random_state,
            verbosity=0,
        )
        self._fitted = False

    def fit(self, frame: pd.DataFrame) -> BttsXGBoostModel:
        """Fit the XGBoost classifier on the provided training frame.

        The frame MUST contain the `btts` target and the model's feature columns.
        """
        _validate_training_frame(frame, self.feature_columns)
        X = frame[self.feature_columns]
        y = frame["btts"]
        # handle class imbalance conservatively: compute scale_pos_weight
        pos = int((y == 1).sum())
        neg = int((y == 0).sum())
        if pos > 0 and neg > 0:
            self.model.set_params(scale_pos_weight=float(neg) / float(pos))
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
