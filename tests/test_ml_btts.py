from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from football_prediction_lab.models.ml_btts import (
    blend_probabilities,
    extra_trees_btts,
    hist_gradient_btts,
    logistic_btts,
)

FEATURES = ("home_signal", "away_signal", "rest_days")


def _frame() -> tuple[pd.DataFrame, pd.Series]:
    values = pd.DataFrame(
        {
            "home_signal": np.linspace(0.1, 1.0, 24),
            "away_signal": np.linspace(1.0, 0.1, 24),
            "rest_days": [3, 5, 7, 10] * 6,
        }
    )
    target = pd.Series([0, 1] * 12)
    return values, target


@pytest.mark.parametrize("factory", [logistic_btts, hist_gradient_btts, extra_trees_btts])
def test_models_produce_bounded_probabilities(factory) -> None:
    frame, target = _frame()
    model = factory(feature_columns=FEATURES).fit(frame, target)
    probabilities = model.predict_probability(frame)
    assert probabilities.between(0.0, 1.0).all()
    assert probabilities.index.equals(frame.index)


def test_blend_is_bounded_and_deterministic() -> None:
    first = pd.Series([0.2, 0.4, 0.8])
    second = pd.Series([0.4, 0.6, 0.2])
    result = blend_probabilities({"a": first, "b": second}, {"a": 1.0, "b": 3.0})
    assert result.tolist() == pytest.approx([0.35, 0.55, 0.35])


def test_models_reject_non_finite_features() -> None:
    frame, target = _frame()
    frame.loc[0, "home_signal"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        logistic_btts(feature_columns=FEATURES).fit(frame, target)
