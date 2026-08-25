import numpy as np
import pytest

from football_prediction_lab.evaluation.uncertainty import bootstrap_metric_intervals


def test_bootstrap_intervals_are_deterministic() -> None:
    probabilities = np.array([0.1, 0.2, 0.7, 0.8, 0.6, 0.4])
    actual = np.array([0, 0, 1, 0, 1, 1])

    first = bootstrap_metric_intervals(probabilities, actual, n_resamples=100, seed=7)
    second = bootstrap_metric_intervals(probabilities, actual, n_resamples=100, seed=7)

    assert first == second
    assert set(first["intervals"]) == {"accuracy", "brier_score", "log_loss"}


def test_bootstrap_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="at least 100"):
        bootstrap_metric_intervals([0.5, 0.5], [0, 1], n_resamples=99)
    with pytest.raises(ValueError, match="between 0 and 1"):
        bootstrap_metric_intervals([0.5, 0.5], [0, 1], confidence=1.0)
