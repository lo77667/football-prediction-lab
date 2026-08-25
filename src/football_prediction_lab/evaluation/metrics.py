"""Evaluation metrics for probabilistic binary predictions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss


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
