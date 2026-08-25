"""Gates for controlled model retraining."""

from __future__ import annotations

from dataclasses import dataclass

from football_prediction_lab.evaluation.metrics import BinaryEvaluation


@dataclass(frozen=True)
class RetrainingDecision:
    accepted: bool
    reason: str


def decide_walk_forward_retraining(
    baseline: dict[str, float | int],
    candidate: dict[str, float | int],
    *,
    minimum_folds: int = 3,
    minimum_rows: int = 500,
    require_accuracy_non_decrease: bool = False,
) -> RetrainingDecision:
    """Accept a candidate only when aggregate future folds improve probability scores."""

    if int(candidate.get("folds", 0)) < minimum_folds:
        return RetrainingDecision(False, f"walk-forward has fewer than {minimum_folds} folds")
    if int(candidate.get("rows", 0)) < minimum_rows:
        return RetrainingDecision(False, f"walk-forward has fewer than {minimum_rows} rows")
    if float(candidate["brier_score_mean"]) >= float(baseline["brier_score_mean"]):
        return RetrainingDecision(False, "candidate did not improve mean Brier Score")
    if float(candidate["log_loss_mean"]) >= float(baseline["log_loss_mean"]):
        return RetrainingDecision(False, "candidate did not improve mean Log Loss")
    if require_accuracy_non_decrease and float(candidate["accuracy_mean"]) < float(
        baseline["accuracy_mean"]
    ):
        return RetrainingDecision(False, "candidate accuracy mean decreased")
    return RetrainingDecision(True, "candidate improved both aggregate probability metrics")


def decide_paired_uncertainty_retraining(
    summary: dict[str, float | int],
    *,
    minimum_folds: int = 3,
    minimum_rows: int = 500,
) -> RetrainingDecision:
    """Accept only if paired bootstrap upper bounds favor the candidate on both losses."""

    if int(summary.get("folds", 0)) < minimum_folds:
        return RetrainingDecision(False, f"paired uncertainty has fewer than {minimum_folds} folds")
    if int(summary.get("rows", 0)) < minimum_rows:
        return RetrainingDecision(False, f"paired uncertainty has fewer than {minimum_rows} rows")
    if float(summary["brier_delta_percentile_97_5"]) >= 0:
        return RetrainingDecision(False, "Brier paired interval crosses zero")
    if float(summary["log_loss_delta_percentile_97_5"]) >= 0:
        return RetrainingDecision(False, "Log Loss paired interval crosses zero")
    return RetrainingDecision(
        True,
        "paired uncertainty interval favors the candidate on both probability metrics",
    )


def decide_calibration_retraining(
    baseline: dict[str, float | int],
    candidate: dict[str, float | int],
    *,
    minimum_folds: int = 3,
    minimum_rows: int = 500,
) -> RetrainingDecision:
    """Accept calibration only if probability metrics improve and ECE does not worsen."""

    if int(candidate.get("folds", 0)) < minimum_folds:
        return RetrainingDecision(False, f"calibration has fewer than {minimum_folds} folds")
    if int(candidate.get("rows", 0)) < minimum_rows:
        return RetrainingDecision(False, f"calibration has fewer than {minimum_rows} rows")
    if float(candidate["brier_score_mean"]) >= float(baseline["brier_score_mean"]):
        return RetrainingDecision(False, "calibration did not improve mean Brier Score")
    if float(candidate["log_loss_mean"]) >= float(baseline["log_loss_mean"]):
        return RetrainingDecision(False, "calibration did not improve mean Log Loss")
    if float(candidate["ece_10_mean"]) > float(baseline["ece_10_mean"]):
        return RetrainingDecision(False, "calibration worsened mean ECE")
    return RetrainingDecision(
        True,
        "calibration improved Brier and Log Loss without worsening ECE",
    )


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
