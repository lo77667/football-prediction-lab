"""Evaluation metrics for probabilistic binary predictions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, log_loss, roc_auc_score


@dataclass(frozen=True)
class BinaryEvaluation:
    rows: int
    accuracy: float
    brier_score: float
    log_loss: float
    actual_rate: float
    mean_probability: float
    threshold: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def evaluate_binary(
    probabilities: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    threshold: float = 0.5,
) -> BinaryEvaluation:
    """Evaluate probabilities with proper scoring rules and a decision threshold."""

    if not 0 < threshold < 1:
        raise ValueError("threshold must be between 0 and 1")
    probability_array = np.asarray(probabilities, dtype=float)
    actual_array = np.asarray(actual, dtype=int)
    if len(probability_array) != len(actual_array) or len(probability_array) == 0:
        raise ValueError("probabilities and actual must have the same non-zero length")
    outside_bounds = (probability_array < 0) | (probability_array > 1)
    if not np.isfinite(probability_array).all() or outside_bounds.any():
        raise ValueError("probabilities must be finite and within [0, 1]")
    if not np.isin(actual_array, [0, 1]).all():
        raise ValueError("actual values must be binary")

    decisions = (probability_array >= threshold).astype(int)
    clipped = np.clip(probability_array, 1e-15, 1 - 1e-15)
    return BinaryEvaluation(
        rows=len(actual_array),
        accuracy=float(accuracy_score(actual_array, decisions)),
        brier_score=float(np.mean((probability_array - actual_array) ** 2)),
        log_loss=float(log_loss(actual_array, clipped, labels=[0, 1])),
        actual_rate=float(actual_array.mean()),
        mean_probability=float(probability_array.mean()),
        threshold=threshold,
    )


def evaluate_binary_extended(
    probabilities: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    baseline_probability: float | pd.Series | np.ndarray | None = None,
    threshold: float = 0.5,
    expected_rows: int | None = None,
) -> dict[str, float | int | None]:
    """Return core, discrimination, skill, calibration, and coverage diagnostics."""

    result = evaluate_binary(probabilities, actual, threshold=threshold).as_dict()
    probability_array = np.asarray(probabilities, dtype=float)
    actual_array = np.asarray(actual, dtype=int)
    classes = np.unique(actual_array)
    if len(classes) == 2:
        result["roc_auc"] = float(roc_auc_score(actual_array, probability_array))
        result["average_precision"] = float(
            average_precision_score(actual_array, probability_array)
        )
        logits = np.log(
            np.clip(probability_array, 1e-15, 1 - 1e-15)
            / np.clip(1 - probability_array, 1e-15, 1 - 1e-15)
        )
        calibration_model = LogisticRegression(solver="lbfgs", random_state=0)
        calibration_model.fit(logits.reshape(-1, 1), actual_array)
        result["calibration_slope"] = float(calibration_model.coef_[0, 0])
        result["calibration_intercept"] = float(calibration_model.intercept_[0])
    else:
        result["roc_auc"] = None
        result["average_precision"] = None
        result["calibration_slope"] = None
        result["calibration_intercept"] = None

    if baseline_probability is None:
        result["brier_skill_score"] = None
        result["log_loss_skill_score"] = None
    else:
        if np.isscalar(baseline_probability):
            baseline = np.full(len(actual_array), float(baseline_probability))
        else:
            baseline = np.asarray(baseline_probability, dtype=float)
        baseline_metrics = evaluate_binary(baseline, actual_array)
        result["brier_skill_score"] = (
            None
            if baseline_metrics.brier_score == 0
            else float(1 - result["brier_score"] / baseline_metrics.brier_score)
        )
        result["log_loss_skill_score"] = (
            None
            if baseline_metrics.log_loss == 0
            else float(1 - result["log_loss"] / baseline_metrics.log_loss)
        )
    result["valid_rows"] = int(len(actual_array))
    result["coverage"] = (
        1.0 if expected_rows is None else float(len(actual_array) / expected_rows)
    )
    return result


def expected_calibration_error(
    probabilities: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    bins: int = 10,
) -> float:
    """Return weighted absolute calibration gap across equal-width bins."""

    table = reliability_table(probabilities, actual, bins=bins)
    non_empty = table.dropna(subset=["mean_probability", "observed_rate"])
    if non_empty.empty:
        return 0.0
    weights = non_empty["rows"] / non_empty["rows"].sum()
    return float(
        (weights * (non_empty["mean_probability"] - non_empty["observed_rate"]).abs()).sum()
    )


def reliability_table(
    probabilities: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    bins: int = 5,
) -> pd.DataFrame:
    """Return count, mean probability, and observed rate by probability bucket."""

    if bins < 2:
        raise ValueError("bins must be at least 2")
    frame = pd.DataFrame(
        {
            "probability": np.asarray(probabilities, dtype=float),
            "actual": np.asarray(actual, dtype=int),
        }
    )
    frame["bucket"] = pd.cut(
        frame["probability"],
        bins=np.linspace(0.0, 1.0, bins + 1),
        include_lowest=True,
        duplicates="drop",
    )
    return (
        frame.groupby("bucket", observed=False)
        .agg(
            rows=("actual", "size"),
            mean_probability=("probability", "mean"),
            observed_rate=("actual", "mean"),
        )
        .reset_index()
    )
