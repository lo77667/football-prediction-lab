import numpy as np
import pytest

from football_prediction_lab.evaluation.metrics import (
    evaluate_binary,
    expected_calibration_error,
    reliability_table,
)


def test_evaluate_binary_returns_probabilistic_metrics() -> None:
    result = evaluate_binary(
        probabilities=np.array([0.9, 0.2, 0.7, 0.1]),
        actual=np.array([1, 0, 0, 0]),
    )
    assert result.rows == 4
    assert result.accuracy == 0.75
    assert 0 <= result.brier_score <= 1
    assert result.log_loss > 0
    assert result.actual_rate == 0.25


def test_reliability_table_has_requested_buckets() -> None:
    table = reliability_table(
        probabilities=np.array([0.1, 0.2, 0.7, 0.8]),
        actual=np.array([0, 0, 1, 0]),
        bins=4,
    )
    assert len(table) == 4
    assert {"rows", "mean_probability", "observed_rate"}.issubset(table.columns)
    assert int(table["rows"].sum()) == 4


def test_expected_calibration_error_is_bounded() -> None:
    value = expected_calibration_error(
        probabilities=np.array([0.1, 0.2, 0.7, 0.8]),
        actual=np.array([0, 0, 1, 0]),
        bins=4,
    )
    assert 0 <= value <= 1


def test_evaluate_binary_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        evaluate_binary([1.2], [1])
