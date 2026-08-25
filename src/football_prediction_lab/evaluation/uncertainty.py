"""Deterministic bootstrap uncertainty intervals for binary model metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary


def bootstrap_metric_intervals(
    probabilities: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    n_resamples: int = 1_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, object]:
    """Return percentile bootstrap intervals without changing the original evaluation."""

    if n_resamples < 100:
        raise ValueError("n_resamples must be at least 100")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    probability_array = np.asarray(probabilities, dtype=float)
    actual_array = np.asarray(actual, dtype=int)
    base = evaluate_binary(probability_array, actual_array).as_dict()
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {
        "accuracy": [],
        "brier_score": [],
        "log_loss": [],
    }
    for _ in range(n_resamples):
        indices = rng.integers(0, len(actual_array), size=len(actual_array))
        evaluation = evaluate_binary(probability_array[indices], actual_array[indices])
        for name in samples:
            samples[name].append(float(getattr(evaluation, name)))
    alpha = (1 - confidence) / 2
    interval: dict[str, dict[str, float]] = {}
    for name, values in samples.items():
        lower, upper = np.quantile(values, [alpha, 1 - alpha])
        interval[name] = {
            "lower": float(lower),
            "upper": float(upper),
        }
    return {
        "base_metrics": base,
        "confidence": confidence,
        "n_resamples": n_resamples,
        "seed": seed,
        "intervals": interval,
    }
