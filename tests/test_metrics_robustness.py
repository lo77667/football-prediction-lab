import numpy as np

from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def test_metrics_handle_probability_boundaries_without_infinite_log_loss() -> None:
    result = evaluate_binary_extended(
        np.array([0.0, 1.0, 0.25, 0.75]),
        np.array([0, 1, 0, 1]),
        baseline_probability=0.5,
        expected_rows=8,
    )
    assert np.isfinite(result["log_loss"])
    assert result["coverage"] == 0.5
    assert result["roc_auc"] == 1.0
    assert result["average_precision"] == 1.0


def test_metrics_fail_closed_for_single_class_discrimination() -> None:
    result = evaluate_binary_extended(
        np.array([0.1, 0.2, 0.3]),
        np.array([0, 0, 0]),
        baseline_probability=0.5,
    )
    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["calibration_slope"] is None
    assert result["calibration_intercept"] is None


def test_metrics_are_deterministic_for_same_inputs() -> None:
    probabilities = np.array([0.15, 0.35, 0.65, 0.85])
    actual = np.array([0, 1, 0, 1])
    first = evaluate_binary_extended(probabilities, actual, baseline_probability=0.5)
    second = evaluate_binary_extended(probabilities, actual, baseline_probability=0.5)
    assert first == second
