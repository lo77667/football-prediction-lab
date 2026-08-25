import pandas as pd
import pytest

from football_prediction_lab.evaluation.calibration_drift import (
    build_calibration_drift_report,
)


def frame(rows_per_slice: int = 4, holdout: bool = False) -> pd.DataFrame:
    seasons = ["2425", "2324"]
    if holdout:
        seasons.append("2526")
    rows: list[dict[str, object]] = []
    for season in seasons:
        for index in range(rows_per_slice):
            rows.append(
                {
                    "season": season,
                    "model_probability": 0.2 if index % 2 == 0 else 0.8,
                    "actual": index % 2,
                }
            )
    return pd.DataFrame(rows)


def test_calibration_drift_marks_small_slices_insufficient() -> None:
    report = build_calibration_drift_report(frame(), minimum_rows=5)
    assert report["status"] == "insufficient_evidence"
    assert report["eligible_slice_count"] == 0
    assert report["economic_claim_status"] == "not_assessed"


def test_calibration_drift_can_mark_stability() -> None:
    report = build_calibration_drift_report(frame(30), minimum_rows=10)
    assert report["status"] == "stable_descriptive"
    assert report["eligible_slice_count"] == 2


def test_calibration_drift_rejects_protected_holdout() -> None:
    with pytest.raises(ValueError, match="protected"):
        build_calibration_drift_report(frame(30, holdout=True), minimum_rows=10)
