"""Descriptive model-versus-market benchmarks and paired uncertainty intervals."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def compare_model_to_market(
    model_probability: pd.Series | np.ndarray,
    market_implied_probability: pd.Series | np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    commission: float = 0.0,
    decimal_odds: pd.Series | np.ndarray | None = None,
) -> dict[str, float | int | None]:
    """Return descriptive market comparison fields; never returns staking instructions."""

    model = np.asarray(model_probability, dtype=float)
    market = np.asarray(market_implied_probability, dtype=float)
    outcome = np.asarray(actual, dtype=int)
    if len(model) == 0 or len(model) != len(market) or len(model) != len(outcome):
        raise ValueError("model, market, and actual must have the same non-zero length")
    if not np.isfinite(market).all() or ((market < 0) | (market > 1)).any():
        raise ValueError("market_implied_probability must be finite and within [0, 1]")
    if not 0.0 <= commission < 1.0:
        raise ValueError("commission must be within [0, 1)")
    result: dict[str, float | int | None] = {
        "rows": int(len(model)),
        "coverage": 1.0,
        "mean_model_probability": float(model.mean()),
        "mean_market_implied_probability": float(market.mean()),
        "mean_raw_edge": float((model - market).mean()),
        "commission": float(commission),
    }
    if decimal_odds is not None:
        odds = np.asarray(decimal_odds, dtype=float)
        if len(odds) != len(model) or not np.isfinite(odds).all() or (odds <= 1).any():
            raise ValueError("decimal_odds must align with valid odds greater than 1")
        result["mean_theoretical_expected_value"] = float(
            np.mean(model * ((odds - 1.0) * (1.0 - commission)) - (1.0 - model))
        )
    return result


def _quantile_interval(values: list[float], confidence: float) -> dict[str, float]:
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(values, [alpha, 1.0 - alpha])
    return {"lower": float(lower), "upper": float(upper)}


def paired_bootstrap_comparison(
    frame: pd.DataFrame,
    *,
    match_column: str = "match_id",
    model_column: str = "model_probability",
    market_column: str = "market_implied_probability",
    actual_column: str = "actual",
    baseline_column: str = "baseline_probability",
    n_resamples: int = 1_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Bootstrap whole matches, preserving paired model/market observations."""

    if n_resamples < 100:
        raise ValueError("n_resamples must be at least 100")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    required = {match_column, model_column, market_column, actual_column, baseline_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing bootstrap columns: {sorted(missing)}")
    if frame[match_column].duplicated().any():
        raise ValueError("paired bootstrap expects one row per match")
    if frame.empty:
        raise ValueError("frame must be non-empty")

    rng = np.random.default_rng(seed)
    rows = frame.reset_index(drop=True)
    samples: dict[str, list[float]] = {
        "roc_auc": [],
        "average_precision": [],
        "brier_skill_score": [],
        "log_loss_skill_score": [],
        "mean_raw_edge": [],
    }
    for _ in range(n_resamples):
        indices = rng.integers(0, len(rows), size=len(rows))
        sample = rows.iloc[indices]
        metrics = evaluate_binary_extended(
            sample[model_column],
            sample[actual_column],
            baseline_probability=sample[baseline_column],
        )
        for name in ("roc_auc", "average_precision", "brier_skill_score", "log_loss_skill_score"):
            value = metrics[name]
            if value is not None:
                samples[name].append(float(value))
        samples["mean_raw_edge"].append(
            float(
                (
                    sample[model_column].to_numpy(dtype=float)
                    - sample[market_column].to_numpy(dtype=float)
                ).mean()
            )
        )

    intervals: dict[str, dict[str, float] | None] = {}
    for name, values in samples.items():
        intervals[name] = _quantile_interval(values, confidence) if values else None
    return {
        "match_rows": int(len(rows)),
        "confidence": confidence,
        "n_resamples": n_resamples,
        "seed": seed,
        "unit": "match_id",
        "intervals": intervals,
    }


def paired_permutation_test(
    frame: pd.DataFrame,
    *,
    reference_column: str = "baseline_probability",
    metric: str = "brier_score",
    actual_column: str = "actual",
    n_permutations: int = 2_000,
    seed: int = 42,
) -> dict[str, float | int | str]:
    """Test paired loss differences by sign permutation, never a profitability test."""

    required = {"match_id", "model_probability", reference_column, actual_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing permutation columns: {sorted(missing)}")
    if frame.empty or frame["match_id"].duplicated().any():
        raise ValueError("paired permutation expects one non-empty row per match")
    if metric not in {"brier_score", "log_loss"}:
        raise ValueError("metric must be brier_score or log_loss")
    if n_permutations < 100:
        raise ValueError("n_permutations must be at least 100")
    model = np.clip(frame["model_probability"].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
    reference = np.clip(frame[reference_column].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
    actual = frame[actual_column].to_numpy(dtype=int)
    if not np.isin(actual, [0, 1]).all():
        raise ValueError("actual values must be binary")
    if metric == "brier_score":
        model_loss = (model - actual) ** 2
        reference_loss = (reference - actual) ** 2
    else:
        model_loss = -(actual * np.log(model) + (1 - actual) * np.log(1 - model))
        reference_loss = -(actual * np.log(reference) + (1 - actual) * np.log(1 - reference))
    differences = reference_loss - model_loss
    observed = float(differences.mean())
    rng = np.random.default_rng(seed)
    null_means = np.empty(n_permutations, dtype=float)
    for index in range(n_permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(differences))
        null_means[index] = float((differences * signs).mean())
    p_value = float(
        (1 + np.count_nonzero(np.abs(null_means) >= abs(observed)))
        / (n_permutations + 1)
    )
    return {
        "metric": metric,
        "reference": reference_column,
        "match_rows": int(len(frame)),
        "unit": "match_id",
        "observed_loss_improvement": observed,
        "p_value_two_sided": p_value,
        "n_permutations": n_permutations,
        "seed": seed,
        "status": "not_significant" if p_value >= 0.05 else "nominal_signal_not_proof",
        "economic_claim_status": "not_assessed",
    }
