"""Descriptive stability checks across predeclared temporal slices."""

from __future__ import annotations

from typing import Any

import pandas as pd

from football_prediction_lab.evaluation.commercial_report import (
    assert_no_protected_holdout,
)
from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def build_slice_stability_report(
    frame: pd.DataFrame,
    *,
    slice_column: str = "season",
    model_column: str = "model_probability",
    actual_column: str = "actual",
    baseline_column: str = "baseline_probability",
    minimum_rows: int = 30,
    protected_seasons: set[str] | None = None,
    max_brier_skill_range: float = 0.10,
    max_roc_auc_range: float = 0.10,
) -> dict[str, Any]:
    """Compare descriptive metrics by slice; never treats stability as profitability."""

    if minimum_rows < 1:
        raise ValueError("minimum_rows must be positive")
    if max_brier_skill_range < 0 or max_roc_auc_range < 0:
        raise ValueError("stability ranges must be non-negative")
    required = {slice_column, model_column, actual_column, baseline_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing stability columns: {sorted(missing)}")
    assert_no_protected_holdout(frame, protected_seasons=protected_seasons)

    slices: list[dict[str, Any]] = []
    for slice_value, group in frame.groupby(slice_column, sort=True, dropna=False):
        metrics = evaluate_binary_extended(
            group[model_column],
            group[actual_column],
            baseline_probability=group[baseline_column],
        )
        sufficient = len(group) >= minimum_rows and metrics["roc_auc"] is not None
        slices.append(
            {
                "slice": str(slice_value),
                "rows": int(len(group)),
                "metrics": metrics,
                "status": "eligible" if sufficient else "insufficient_evidence",
            }
        )

    eligible = [row for row in slices if row["status"] == "eligible"]
    if len(eligible) < 2:
        status = "insufficient_evidence"
        ranges = {"brier_skill_score": None, "roc_auc": None}
    else:
        brier_values = [row["metrics"]["brier_skill_score"] for row in eligible]
        auc_values = [row["metrics"]["roc_auc"] for row in eligible]
        ranges = {
            "brier_skill_score": float(max(brier_values) - min(brier_values)),
            "roc_auc": float(max(auc_values) - min(auc_values)),
        }
        status = (
            "stable_descriptive"
            if ranges["brier_skill_score"] <= max_brier_skill_range
            and ranges["roc_auc"] <= max_roc_auc_range
            else "unstable"
        )
    return {
        "slice_column": slice_column,
        "minimum_rows": minimum_rows,
        "protected_seasons": sorted(protected_seasons or {"2526"}),
        "slices": slices,
        "eligible_slice_count": len(eligible),
        "ranges": ranges,
        "status": status,
        "economic_claim_status": "not_assessed",
    }
