"""Small-data modeling utilities for quantitative and hybrid player features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ModelName = Literal["logistic", "random_forest", "hist_gradient_boosting"]


@dataclass(frozen=True)
class TemporalEvaluation:
    """Evaluation result for one model on a future holdout."""

    model_name: str
    n_train: int
    n_test: int
    roc_auc: float | None
    brier_score: float | None
    accuracy: float


def temporal_holdout_indices(
    cutoffs: pd.Series | list[object], *, test_fraction: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Return chronological train/test indices without shuffling."""

    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    timestamps = pd.to_datetime(cutoffs, utc=True, errors="raise")
    order = np.argsort(timestamps.to_numpy())
    split_at = int(len(order) * (1 - test_fraction))
    if split_at <= 0 or split_at >= len(order):
        raise ValueError("not enough rows for a temporal holdout")
    return order[:split_at], order[split_at:]


def build_estimator(model_name: ModelName = "logistic") -> Pipeline:
    """Build a conservative estimator suitable for small-to-medium datasets."""

    if model_name == "logistic":
        estimator = LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            C=0.5,
            random_state=42,
        )
        scale = StandardScaler()
    elif model_name == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=300,
            max_depth=5,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        scale = "passthrough"
    elif model_name == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(
            max_iter=150,
            learning_rate=0.05,
            max_leaf_nodes=7,
            l2_regularization=1.0,
            random_state=42,
        )
        scale = "passthrough"
    else:
        raise ValueError(f"unsupported model_name: {model_name}")
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", scale),
            ("estimator", estimator),
        ]
    )


def _as_numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce boolean flags and numeric feature columns without accepting text."""

    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == bool:
            result[column] = result[column].astype(float)
    return result.apply(pd.to_numeric, errors="raise")


def evaluate_ablation(
    quantitative: pd.DataFrame,
    qualitative: pd.DataFrame,
    y: pd.Series | np.ndarray,
    cutoffs: pd.Series | list[object],
    *,
    model_name: ModelName = "logistic",
    test_fraction: float = 0.2,
) -> list[TemporalEvaluation]:
    """Compare quantitative-only and combined features on a future holdout.

    ``qualitative`` must already be generated using events available at each row's
    prediction cutoff. This function deliberately does not perform any joins or
    imputation using future rows.
    """

    q = _as_numeric_frame(quantitative)
    qual = _as_numeric_frame(qualitative)
    if len(q) != len(qual) or len(q) != len(y) or len(q) != len(cutoffs):
        raise ValueError("quantitative, qualitative, y, and cutoffs must have equal length")
    train_idx, test_idx = temporal_holdout_indices(cutoffs, test_fraction=test_fraction)
    y_array = np.asarray(y)
    evaluations: list[TemporalEvaluation] = []
    for label, features in (("quantitative_only", q), ("hybrid", pd.concat([q, qual], axis=1))):
        estimator = build_estimator(model_name)
        estimator.fit(features.iloc[train_idx], y_array[train_idx])
        predictions = estimator.predict(features.iloc[test_idx])
        probabilities = estimator.predict_proba(features.iloc[test_idx])[:, 1]
        y_test = y_array[test_idx]
        auc = None
        brier = None
        if len(np.unique(y_test)) == 2:
            auc = float(roc_auc_score(y_test, probabilities))
            brier = float(brier_score_loss(y_test, probabilities))
        evaluations.append(
            TemporalEvaluation(
                model_name=label,
                n_train=len(train_idx),
                n_test=len(test_idx),
                roc_auc=auc,
                brier_score=brier,
                accuracy=float(accuracy_score(y_test, predictions)),
            )
        )
    return evaluations
