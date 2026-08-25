"""Probability calibration helpers with explicit disjoint calibration data."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

_EPSILON = 1e-6


def platt_calibrate(
    calibration_probability: pd.Series,
    calibration_target: pd.Series,
    prediction_probability: pd.Series,
    *,
    c_value: float = 1.0,
) -> pd.Series:
    """Fit a sigmoid mapping on a disjoint calibration set."""

    if c_value <= 0:
        raise ValueError("c_value must be positive")
    calibration_logit = _logit(calibration_probability.to_numpy())
    prediction_logit = _logit(prediction_probability.to_numpy())
    calibrator = LogisticRegression(solver="lbfgs", C=c_value, max_iter=1_000)
    calibrator.fit(calibration_logit.reshape(-1, 1), calibration_target.to_numpy())
    calibrated = calibrator.predict_proba(prediction_logit.reshape(-1, 1))[:, 1]
    return pd.Series(calibrated, index=prediction_probability.index)


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability.astype(float), _EPSILON, 1.0 - _EPSILON)
    return np.log(clipped / (1.0 - clipped))
