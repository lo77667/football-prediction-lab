"""Point-in-time comparison of raw probabilities and Platt calibration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def compare_raw_and_platt(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    cutoff: datetime,
    probability_column: str = "model_probability",
    actual_column: str = "actual",
    kickoff_column: str = "kickoff_utc",
    season_column: str = "season",
    protected_seasons: set[str] | None = None,
) -> dict[str, Any]:
    """Fit Platt only on pre-cutoff data and evaluate only on post-cutoff data."""

    protected = protected_seasons or {"2526"}
    required = {probability_column, actual_column, kickoff_column, season_column}
    for name, frame in (("train", train), ("test", test)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"missing calibration columns in {name}: {sorted(missing)}")
        if frame.empty:
            raise ValueError(f"{name} frame must be non-empty")
        if frame[season_column].astype(str).isin(protected).any():
            raise ValueError(f"protected season present in {name} calibration frame")
    cutoff_utc = pd.Timestamp(cutoff)
    train_kickoff = pd.to_datetime(train[kickoff_column], utc=True)
    test_kickoff = pd.to_datetime(test[kickoff_column], utc=True)
    if not (train_kickoff < cutoff_utc).all():
        raise ValueError("training rows must be strictly before cutoff")
    if not (test_kickoff >= cutoff_utc).all():
        raise ValueError("test rows must be on or after cutoff")

    train_probability = np.clip(train[probability_column].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
    test_probability = np.clip(test[probability_column].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
    train_logits = np.log(train_probability / (1 - train_probability))
    test_logits = np.log(test_probability / (1 - test_probability))
    calibrator = LogisticRegression(solver="lbfgs", random_state=0)
    calibrator.fit(train_logits.reshape(-1, 1), train[actual_column].to_numpy(dtype=int))
    platt_probability = calibrator.predict_proba(test_logits.reshape(-1, 1))[:, 1]
    actual = test[actual_column]
    raw_metrics = evaluate_binary_extended(test_probability, actual)
    platt_metrics = evaluate_binary_extended(platt_probability, actual)
    return {
        "cutoff": cutoff_utc.isoformat(),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "raw": raw_metrics,
        "platt": platt_metrics,
        "economic_claim_status": "not_assessed",
        "holdout_protected": True,
    }
