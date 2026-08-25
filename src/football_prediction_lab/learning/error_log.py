"""Structured error logging for controlled retraining cycles."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ERROR_COLUMNS = [
    "prediction_id",
    "match_id",
    "probability_yes",
    "actual_yes",
    "decision",
    "correct_decision",
    "absolute_error",
    "error_type",
    "confidence_band",
]


def classify_errors(evaluation: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic error categories without changing historical predictions."""

    required = {
        "prediction_id",
        "match_id",
        "probability_yes",
        "actual_yes",
        "decision",
        "correct_decision",
        "absolute_error",
    }
    missing = required.difference(evaluation.columns)
    if missing:
        raise ValueError(f"Missing evaluation columns: {sorted(missing)}")

    result = evaluation.copy()
    result["error_type"] = "correct"
    false_positive = (result["decision"] == 1) & (result["actual_yes"] == 0)
    false_negative = (result["decision"] == 0) & (result["actual_yes"] == 1)
    result.loc[false_positive, "error_type"] = "false_positive"
    result.loc[false_negative, "error_type"] = "false_negative"
    result["confidence_band"] = pd.cut(
        result["probability_yes"],
        bins=[-0.001, 0.4, 0.6, 1.001],
        labels=["low", "medium", "high"],
        include_lowest=True,
    ).astype("string")
    return result[ERROR_COLUMNS]


def write_learning_cycle(
    path: Path,
    *,
    source_evaluation: str,
    parent_model_version: str,
    candidate_model_version: str,
    accepted: bool,
    reason: str,
) -> None:
    """Append a human-readable retraining decision to an immutable-style log."""

    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "source_evaluation": source_evaluation,
        "parent_model_version": parent_model_version,
        "candidate_model_version": candidate_model_version,
        "accepted": accepted,
        "reason": reason,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
