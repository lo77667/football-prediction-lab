from football_prediction_lab.evaluation.metrics import BinaryEvaluation
from football_prediction_lab.learning.retraining import decide_retraining


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
