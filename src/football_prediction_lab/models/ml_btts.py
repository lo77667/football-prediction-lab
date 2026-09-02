"""Leakage-safe tabular BTTS models and probability ensemble."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from football_prediction_lab.features.pre_match import FEATURE_COLUMNS


@dataclass(frozen=True)
class MLModelConfig:
    """Conservative defaults for small, time-ordered football datasets."""

    random_state: int = 42
    min_samples_leaf: int = 8
    max_iter: int = 250


class _ValidatedModel:
    """Shared validation and prediction contract for binary probability models."""

    def __init__(self, estimator: Any, feature_columns: tuple[str, ...]) -> None:
        self.estimator = estimator
        self.feature_columns = feature_columns
        self._fitted = False

    def fit(self, frame: pd.DataFrame, target: pd.Series | np.ndarray) -> _ValidatedModel:
        values = _validated_matrix(frame, self.feature_columns)
        labels = np.asarray(target, dtype=int)
        if len(values) != len(labels) or len(labels) < 2:
            raise ValueError("training features and target must have at least two aligned rows")
        if np.unique(labels).size < 2:
            raise ValueError("training target must contain both binary classes")
        self.estimator.fit(values, labels)
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        values = _validated_matrix(frame, self.feature_columns)
        probabilities = self.estimator.predict_proba(values)[:, 1]
        return pd.Series(
            np.clip(probabilities, 0.0, 1.0), index=frame.index, name="probability_yes"
        )


def _validated_matrix(frame: pd.DataFrame, feature_columns: tuple[str, ...]) -> np.ndarray:
    missing = sorted(set(feature_columns).difference(frame.columns))
    if missing:
        raise ValueError(f"missing pre-match features: {missing}")
    values = frame[list(feature_columns)].apply(pd.to_numeric, errors="coerce")
    matrix = values.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("pre-match features must be finite")
    return matrix


def _columns(frame: pd.DataFrame) -> tuple[str, ...]:
    selected = tuple(column for column in FEATURE_COLUMNS if column in frame.columns)
    if not selected:
        raise ValueError("frame has no recognized pre-match features")
    return selected


def logistic_btts(
    config: MLModelConfig | None = None, *, feature_columns: tuple[str, ...] | None = None
) -> _ValidatedModel:
    """Regularized, interpretable baseline."""
    settings = config or MLModelConfig()
    columns = feature_columns or tuple(FEATURE_COLUMNS)
    estimator = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=0.5,
            max_iter=settings.max_iter,
            class_weight="balanced",
            random_state=settings.random_state,
        ),
    )
    return _ValidatedModel(estimator, columns)


def hist_gradient_btts(
    config: MLModelConfig | None = None, *, feature_columns: tuple[str, ...] | None = None
) -> _ValidatedModel:
    """Regularized nonlinear model without optional native dependencies."""
    settings = config or MLModelConfig()
    columns = feature_columns or tuple(FEATURE_COLUMNS)
    estimator = HistGradientBoostingClassifier(
        max_iter=settings.max_iter,
        learning_rate=0.04,
        max_leaf_nodes=15,
        min_samples_leaf=settings.min_samples_leaf,
        l2_regularization=1.0,
        random_state=settings.random_state,
    )
    return _ValidatedModel(estimator, columns)


def extra_trees_btts(
    config: MLModelConfig | None = None, *, feature_columns: tuple[str, ...] | None = None
) -> _ValidatedModel:
    """Randomized tree ensemble for nonlinear interactions."""
    settings = config or MLModelConfig()
    columns = feature_columns or tuple(FEATURE_COLUMNS)
    estimator = ExtraTreesClassifier(
        n_estimators=300,
        min_samples_leaf=settings.min_samples_leaf,
        class_weight="balanced",
        random_state=settings.random_state,
        n_jobs=1,
    )
    return _ValidatedModel(estimator, columns)


def blend_probabilities(
    probabilities: dict[str, pd.Series], weights: dict[str, float] | None = None
) -> pd.Series:
    """Blend already out-of-fold probabilities; weights must be chosen in inner folds."""
    if not probabilities:
        raise ValueError("at least one probability series is required")
    keys = list(probabilities)
    weights = weights or {key: 1.0 / len(keys) for key in keys}
    if set(weights) != set(keys) or any(value < 0 for value in weights.values()):
        raise ValueError("weights must cover all models and be non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must have a positive sum")
    aligned = pd.concat([probabilities[key].rename(key) for key in keys], axis=1)
    result = sum((weights[key] / total) * aligned[key] for key in keys)
    return result.clip(0.0, 1.0).rename("probability_yes")


def model_registry(
    config: MLModelConfig | None = None, *, feature_columns: tuple[str, ...] | None = None
) -> dict[str, _ValidatedModel]:
    """Return the candidate set used by time-ordered evaluation."""
    return {
        "logistic": logistic_btts(config, feature_columns=feature_columns),
        "hist_gradient": hist_gradient_btts(config, feature_columns=feature_columns),
        "extra_trees": extra_trees_btts(config, feature_columns=feature_columns),
    }


__all__ = [
    "MLModelConfig",
    "blend_probabilities",
    "extra_trees_btts",
    "hist_gradient_btts",
    "logistic_btts",
    "model_registry",
]


# Keep this helper exercised by callers that construct frames dynamically.
def feature_columns_from_frame(frame: pd.DataFrame) -> tuple[str, ...]:
    return _columns(frame)
