import pytest

from football_prediction_lab.agent.explanation import VerifiedEvaluation, render_verified_summary


def test_agent_summary_contains_only_verified_metrics() -> None:
    evaluation = VerifiedEvaluation(
        market="btts",
        model_version="v0",
        rows=57,
        accuracy=0.5088,
        brier_score=0.2562,
        log_loss=0.7060,
        actual_rate=0.5088,
        mean_probability=0.5044,
    )
    summary = render_verified_summary(evaluation)
    assert "57" in summary
    assert "0.5088" in summary
    assert "لا يثبت ربحية" in summary


def test_agent_rejects_unsupported_market() -> None:
    with pytest.raises(ValueError, match="unsupported market"):
        VerifiedEvaluation(
            market="winner",
            model_version="v0",
            rows=10,
            accuracy=0.5,
            brier_score=0.25,
            log_loss=0.69,
            actual_rate=0.5,
            mean_probability=0.5,
        )
