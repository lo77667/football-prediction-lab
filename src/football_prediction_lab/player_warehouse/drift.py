"""Feature-drift detection for the training baseline versus current player data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp


@dataclass(frozen=True)
class DriftResult:
    """One feature's current-versus-training distribution comparison."""

    feature_name: str
    baseline_n: int
    current_n: int
    baseline_missing_rate: float
    current_missing_rate: float
    ks_statistic: float | None
    ks_p_value: float | None
    psi: float | None
    drift_status: str
    compared_at_utc: datetime


def population_stability_index(
    baseline: pd.Series,
    current: pd.Series,
    *,
    bins: int = 10,
    epsilon: float = 1e-6,
) -> float | None:
    """Calculate PSI using quantile bins learned from the baseline only."""

    expected = pd.to_numeric(baseline, errors="coerce").dropna().to_numpy(dtype=float)
    actual = pd.to_numeric(current, errors="coerce").dropna().to_numpy(dtype=float)
    if len(expected) == 0 or len(actual) == 0:
        return None
    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(expected, quantiles))
    if len(edges) < 2:
        return 0.0 if np.isclose(np.mean(expected), np.mean(actual)) else float("inf")
    edges[0] = -np.inf
    edges[-1] = np.inf
    expected_counts, _ = np.histogram(expected, bins=edges)
    actual_counts, _ = np.histogram(actual, bins=edges)
    expected_pct = np.maximum(expected_counts / len(expected), epsilon)
    actual_pct = np.maximum(actual_counts / len(actual), epsilon)
    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))


def detect_feature_drift(
    baseline: pd.Series,
    current: pd.Series,
    *,
    feature_name: str,
    alpha: float = 0.01,
    psi_threshold: float = 0.20,
    min_sample_size: int = 20,
    compared_at_utc: datetime | None = None,
) -> DriftResult:
    """Compare one current distribution against the locked training baseline.

    Drift is flagged when the KS p-value is below ``alpha``, PSI exceeds its
    threshold, or missingness changes by at least five percentage points. Small
    samples are marked ``insufficient_data`` rather than treated as stable.
    """

    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if psi_threshold < 0:
        raise ValueError("psi_threshold cannot be negative")
    if min_sample_size < 2:
        raise ValueError("min_sample_size must be at least 2")
    comparison_time = compared_at_utc or datetime.now().astimezone()
    baseline_numeric = pd.to_numeric(baseline, errors="coerce")
    current_numeric = pd.to_numeric(current, errors="coerce")
    baseline_valid = baseline_numeric.dropna()
    current_valid = current_numeric.dropna()
    baseline_missing_rate = float(baseline_numeric.isna().mean())
    current_missing_rate = float(current_numeric.isna().mean())
    if len(baseline_valid) < min_sample_size or len(current_valid) < min_sample_size:
        return DriftResult(
            feature_name=feature_name,
            baseline_n=len(baseline_valid),
            current_n=len(current_valid),
            baseline_missing_rate=baseline_missing_rate,
            current_missing_rate=current_missing_rate,
            ks_statistic=None,
            ks_p_value=None,
            psi=None,
            drift_status="insufficient_data",
            compared_at_utc=comparison_time,
        )
    ks = ks_2samp(baseline_valid, current_valid, alternative="two-sided", mode="auto")
    psi = population_stability_index(baseline_valid, current_valid)
    missingness_drift = abs(current_missing_rate - baseline_missing_rate) >= 0.05
    is_drift = (
        float(ks.pvalue) < alpha or (psi is not None and psi >= psi_threshold) or missingness_drift
    )
    return DriftResult(
        feature_name=feature_name,
        baseline_n=len(baseline_valid),
        current_n=len(current_valid),
        baseline_missing_rate=baseline_missing_rate,
        current_missing_rate=current_missing_rate,
        ks_statistic=float(ks.statistic),
        ks_p_value=float(ks.pvalue),
        psi=psi,
        drift_status="drift" if is_drift else "stable",
        compared_at_utc=comparison_time,
    )


def build_drift_report(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    feature_names: Iterable[str] = ("confidence_score", "player_load_au"),
    alpha: float = 0.01,
    psi_threshold: float = 0.20,
    min_sample_size: int = 20,
    compared_at_utc: datetime | None = None,
) -> pd.DataFrame:
    """Build a dashboard-ready drift table for several numeric features."""

    features = list(feature_names)
    missing_baseline = set(features) - set(baseline.columns)
    missing_current = set(features) - set(current.columns)
    if missing_baseline or missing_current:
        raise ValueError(
            "missing features; "
            f"baseline={sorted(missing_baseline)}, current={sorted(missing_current)}"
        )
    results = [
        detect_feature_drift(
            baseline[feature],
            current[feature],
            feature_name=feature,
            alpha=alpha,
            psi_threshold=psi_threshold,
            min_sample_size=min_sample_size,
            compared_at_utc=compared_at_utc,
        )
        for feature in features
    ]
    return pd.DataFrame([result.__dict__ for result in results])
