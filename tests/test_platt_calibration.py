import pandas as pd
import pytest

from football_prediction_lab.learning.calibration import platt_calibrate


def test_platt_calibrate_returns_bounded_probabilities() -> None:
    calibration_probability = pd.Series([0.1, 0.2, 0.7, 0.8, 0.9, 0.95])
    calibration_target = pd.Series([0, 0, 1, 1, 1, 1])
    prediction_probability = pd.Series([0.01, 0.5, 0.99], index=[4, 5, 6])

    calibrated = platt_calibrate(
        calibration_probability,
        calibration_target,
        prediction_probability,
    )

    assert list(calibrated.index) == [4, 5, 6]
    assert ((calibrated > 0) & (calibrated < 1)).all()


def test_platt_calibrate_rejects_non_positive_c() -> None:
    with pytest.raises(ValueError, match="c_value must be positive"):
        platt_calibrate(
            pd.Series([0.2, 0.8]),
            pd.Series([0, 1]),
            pd.Series([0.5]),
            c_value=0,
        )
