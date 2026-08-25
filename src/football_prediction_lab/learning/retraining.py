"""Gates for controlled model retraining."""

from __future__ import annotations

from dataclasses import dataclass

from football_prediction_lab.evaluation.metrics import BinaryEvaluation


@dataclass(frozen=True)
class RetrainingDecision:
    accepted: bool
    reason: str


def decide_retraining(
    baseline: BinaryEvaluation,
    candidate: BinaryEvaluation,
    *,
    minimum_test_rows: int = 100,
    tolerance: float = 1e-9,
) -> RetrainingDecision:
    """Accept only a candidate that improves Brier and Log Loss on enough future data."""

    if candidate.rows < minimum_test_rows:
        return RetrainingDecision(
            accepted=False,
            reason=f"untouched test window has fewer than {minimum_test_rows} rows",
        )
    if candidate.brier_score > baseline.brier_score - tolerance:
        return RetrainingDecision(
            accepted=False,
            reason="candidate did not improve Brier Score beyond tolerance",
        )
    if candidate.log_loss > baseline.log_loss - tolerance:
        return RetrainingDecision(
            accepted=False,
            reason="candidate did not improve Log Loss beyond tolerance",
        )
    return RetrainingDecision(
        accepted=True,
        reason="candidate improved Brier Score and Log Loss on the untouched test window",
    )
