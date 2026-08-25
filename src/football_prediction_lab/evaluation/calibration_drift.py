"""Descriptive calibration-drift checks across temporal slices."""

from __future__ import annotations

from typing import Any

import pandas as pd

from football_prediction_lab.evaluation.commercial_report import (
    assert_no_protected_holdout,
)
from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def build_calibration_drift_report(
    frame: pd.DataFrame,
    *,
    slice_column: str = "season",
    model_column: str = "model_probability",
    actual_column: str = "actual",
    minimum_rows: int = 30,
    protected_seasons: set[str] | None = None,
    max_slope_range: float = 0.25,
    max_intercept_range: float = 0.25,
) -> dict[str, Any]:
    """Report calibration parameter drift; it is not a profitability assessment."""

    if minimum_rows < 1:
        raise ValueError("minimum_rows must be positive")
    if max_slope_range < 0 or max_intercept_range < 0:
        raise ValueError("drift ranges must be non-negative")
    required = {slice_column, model_column, actual_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing calibration drift columns: {sorted(missing)}")
    assert_no_protected_holdout(frame, protected_seasons=protected_seasons)

    slices: list[dict[str, Any]] = []
    for slice_value, group in frame.groupby(slice_column, sort=True, dropna=False):
        metrics = evaluate_binary_extended(group[model_column], group[actual_column])
        slope = metrics["calibration_slope"]
        intercept = metrics["calibration_intercept"]
        eligible = len(group) >= minimum_rows and slope is not None and intercept is not None
        slices.append(
            {
                "slice": str(slice_value),
                "rows": int(len(group)),
                "calibration_slope": slope,
                "calibration_intercept": intercept,
                "status": "eligible" if eligible else "insufficient_evidence",
            }
        )

    eligible_slices = [row for row in slices if row["status"] == "eligible"]
    if len(eligible_slices) < 2:
        ranges = {"calibration_slope": None, "calibration_intercept": None}
        status = "insufficient_evidence"
    else:
        slopes = [row["calibration_slope"] for row in eligible_slices]
        intercepts = [row["calibration_intercept"] for row in eligible_slices]
        ranges = {
            "calibration_slope": float(max(slopes) - min(slopes)),
            "calibration_intercept": float(max(intercepts) - min(intercepts)),
        }
        status = (
            "stable_descriptive"
            if ranges["calibration_slope"] <= max_slope_range
            and ranges["calibration_intercept"] <= max_intercept_range
            else "drift_detected"
        )
    return {
        "slice_column": slice_column,
        "minimum_rows": minimum_rows,
        "protected_seasons": sorted(protected_seasons or {"2526"}),
        "slices": slices,
        "eligible_slice_count": len(eligible_slices),
        "ranges": ranges,
        "status": status,
        "economic_claim_status": "not_assessed",
    }
