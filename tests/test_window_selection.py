import pytest

from football_prediction_lab.learning.window_selection import select_window


def test_select_window_prefers_validation_brier_then_log_loss() -> None:
    selected = select_window(
        {
            3: {"brier_score": 0.24, "log_loss": 0.68},
            5: {"brier_score": 0.23, "log_loss": 0.72},
            10: {"brier_score": 0.23, "log_loss": 0.69},
        }
    )

    assert selected.window == 10
    assert selected.validation_brier_score == 0.23
    assert selected.validation_log_loss == 0.69


def test_select_window_breaks_complete_ties_with_smaller_window() -> None:
    selected = select_window(
        {
            5: {"brier_score": 0.25, "log_loss": 0.69},
            3: {"brier_score": 0.25, "log_loss": 0.69},
        }
    )

    assert selected.window == 3


def test_select_window_rejects_empty_or_incomplete_scores() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        select_window({})
    with pytest.raises(ValueError, match="missing validation metrics"):
        select_window({5: {"brier_score": 0.25}})
