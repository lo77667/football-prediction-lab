from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from football_prediction_lab.evaluation.calibration_compare import (
    compare_raw_and_platt,
)

CUTOFF = datetime(2025, 8, 1, tzinfo=UTC)


def frame(start: datetime, rows: int, season: str = "2425") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "kickoff_utc": [start + timedelta(days=index) for index in range(rows)],
            "season": [season] * rows,
            "model_probability": [0.2, 0.3, 0.7, 0.8] * (rows // 4),
            "actual": [0, 0, 1, 1] * (rows // 4),
        }
    )


def test_raw_vs_platt_is_point_in_time_and_descriptive() -> None:
    train = frame(CUTOFF - timedelta(days=20), 20)
    test = frame(CUTOFF + timedelta(days=1), 20)
    report = compare_raw_and_platt(train, test, cutoff=CUTOFF)
    assert report["train_rows"] == 20
    assert report["test_rows"] == 20
    assert report["economic_claim_status"] == "not_assessed"
    assert report["holdout_protected"] is True


def test_calibration_compare_rejects_future_training_rows() -> None:
    train = frame(CUTOFF + timedelta(days=1), 20)
    test = frame(CUTOFF + timedelta(days=2), 20)
    with pytest.raises(ValueError, match="before cutoff"):
        compare_raw_and_platt(train, test, cutoff=CUTOFF)


def test_calibration_compare_rejects_protected_season() -> None:
    train = frame(CUTOFF - timedelta(days=20), 20, season="2526")
    test = frame(CUTOFF + timedelta(days=1), 20)
    with pytest.raises(ValueError, match="protected"):
        compare_raw_and_platt(train, test, cutoff=CUTOFF)
