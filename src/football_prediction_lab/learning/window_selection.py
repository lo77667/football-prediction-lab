"""Deterministic nested selection of rolling-window candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowSelection:
    window: int
    validation_brier_score: float
    validation_log_loss: float


def select_window(validation_scores: Mapping[int, Mapping[str, float]]) -> WindowSelection:
    """Select a window using validation metrics only.

    The caller must calculate each score without using the future test season. The
    deterministic tie-break order is Brier Score, Log Loss, then the smaller window.
    """

    if not validation_scores:
        raise ValueError("validation_scores must not be empty")
    required = {"brier_score", "log_loss"}
    for window, scores in validation_scores.items():
        if window < 1:
            raise ValueError("window must be positive")
        missing = required.difference(scores)
        if missing:
            raise ValueError(f"missing validation metrics: {sorted(missing)}")

    selected_window = min(
        validation_scores,
        key=lambda window: (
            float(validation_scores[window]["brier_score"]),
            float(validation_scores[window]["log_loss"]),
            int(window),
        ),
    )
    selected = validation_scores[selected_window]
    return WindowSelection(
        window=int(selected_window),
        validation_brier_score=float(selected["brier_score"]),
        validation_log_loss=float(selected["log_loss"]),
    )
