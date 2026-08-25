from football_prediction_lab.evaluation.metrics import BinaryEvaluation
from football_prediction_lab.learning.retraining import (
    decide_calibration_retraining,
    decide_paired_uncertainty_retraining,
    decide_retraining,
    decide_walk_forward_retraining,
)


def _evaluation(*, rows: int, brier: float, log_loss: float) -> BinaryEvaluation:
    return BinaryEvaluation(
        rows=rows,
        accuracy=0.5,
        brier_score=brier,
        log_loss=log_loss,
        actual_rate=0.5,
        mean_probability=0.5,
        threshold=0.5,
    )


def test_walk_forward_gate_rejects_small_fold_count() -> None:
    decision = decide_walk_forward_retraining(
        {
            "folds": 3,
            "rows": 600,
            "accuracy_mean": 0.5,
            "brier_score_mean": 0.25,
            "log_loss_mean": 0.69,
        },
        {
            "folds": 2,
            "rows": 600,
            "accuracy_mean": 0.6,
            "brier_score_mean": 0.20,
            "log_loss_mean": 0.65,
        },
    )
    assert decision.accepted is False
    assert "folds" in decision.reason


def test_walk_forward_gate_requires_both_probability_metrics() -> None:
    decision = decide_walk_forward_retraining(
        {
            "folds": 3,
            "rows": 600,
            "accuracy_mean": 0.5,
            "brier_score_mean": 0.25,
            "log_loss_mean": 0.69,
        },
        {
            "folds": 3,
            "rows": 600,
            "accuracy_mean": 0.6,
            "brier_score_mean": 0.20,
            "log_loss_mean": 0.70,
        },
    )
    assert decision.accepted is False
    assert "Log Loss" in decision.reason


def test_walk_forward_gate_accepts_both_probability_improvements() -> None:
    decision = decide_walk_forward_retraining(
        {
            "folds": 3,
            "rows": 600,
            "accuracy_mean": 0.5,
            "brier_score_mean": 0.25,
            "log_loss_mean": 0.69,
        },
        {
            "folds": 3,
            "rows": 600,
            "accuracy_mean": 0.5,
            "brier_score_mean": 0.20,
            "log_loss_mean": 0.65,
        },
    )
    assert decision.accepted is True


def test_paired_uncertainty_gate_rejects_interval_crossing_zero() -> None:
    decision = decide_paired_uncertainty_retraining(
        {
            "folds": 8,
            "rows": 3_040,
            "brier_delta_percentile_97_5": 0.0009,
            "log_loss_delta_percentile_97_5": 0.0019,
        }
    )
    assert decision.accepted is False
    assert "Brier" in decision.reason


def test_paired_uncertainty_gate_rejects_log_loss_interval_crossing_zero() -> None:
    decision = decide_paired_uncertainty_retraining(
        {
            "folds": 8,
            "rows": 3_040,
            "brier_delta_percentile_97_5": -0.0001,
            "log_loss_delta_percentile_97_5": 0.0002,
        }
    )
    assert decision.accepted is False
    assert "Log Loss" in decision.reason


def test_paired_uncertainty_gate_accepts_strictly_negative_bounds() -> None:
    decision = decide_paired_uncertainty_retraining(
        {
            "folds": 8,
            "rows": 3_040,
            "brier_delta_percentile_97_5": -0.0001,
            "log_loss_delta_percentile_97_5": -0.0002,
        }
    )
    assert decision.accepted is True


def test_paired_uncertainty_gate_rejects_small_sample() -> None:
    decision = decide_paired_uncertainty_retraining(
        {
            "folds": 2,
            "rows": 100,
            "brier_delta_percentile_97_5": -0.01,
            "log_loss_delta_percentile_97_5": -0.01,
        }
    )
    assert decision.accepted is False
    assert "fewer" in decision.reason


def test_calibration_gate_rejects_log_loss_regression() -> None:
    decision = decide_calibration_retraining(
        {
            "folds": 8,
            "rows": 3_000,
            "brier_score_mean": 0.255,
            "log_loss_mean": 0.705,
            "ece_10_mean": 0.072,
        },
        {
            "folds": 8,
            "rows": 3_000,
            "brier_score_mean": 0.252,
            "log_loss_mean": 0.856,
            "ece_10_mean": 0.045,
        },
    )
    assert decision.accepted is False
    assert "Log Loss" in decision.reason


def test_calibration_gate_accepts_all_required_improvements() -> None:
    decision = decide_calibration_retraining(
        {
            "folds": 8,
            "rows": 3_000,
            "brier_score_mean": 0.255,
            "log_loss_mean": 0.705,
            "ece_10_mean": 0.072,
        },
        {
            "folds": 8,
            "rows": 3_000,
            "brier_score_mean": 0.252,
            "log_loss_mean": 0.700,
            "ece_10_mean": 0.045,
        },
    )
    assert decision.accepted is True


def test_retraining_rejects_small_test_window() -> None:
    decision = decide_retraining(
        _evaluation(rows=57, brier=0.25, log_loss=0.69),
        _evaluation(rows=57, brier=0.20, log_loss=0.65),
    )
    assert decision.accepted is False
    assert "fewer" in decision.reason


def test_retraining_requires_both_probability_metrics_to_improve() -> None:
    decision = decide_retraining(
        _evaluation(rows=120, brier=0.25, log_loss=0.69),
        _evaluation(rows=120, brier=0.20, log_loss=0.70),
    )
    assert decision.accepted is False
    assert "Log Loss" in decision.reason


def test_retraining_accepts_candidate_with_both_improvements() -> None:
    decision = decide_retraining(
        _evaluation(rows=120, brier=0.25, log_loss=0.69),
        _evaluation(rows=120, brier=0.20, log_loss=0.65),
    )
    assert decision.accepted is True
