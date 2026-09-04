from __future__ import annotations

import pandas as pd
import pytest

from football_prediction_lab.models.dixon_coles import DixonColesBTTS


def test_dixon_coles_fit_and_predict_is_bounded() -> None:
    train = pd.DataFrame(
        {
            "lambda_home": [1.4, 1.8, 0.9, 1.2, 2.0, 1.1],
            "lambda_away": [0.8, 1.0, 1.1, 0.7, 1.3, 1.5],
            "home_goals": [2, 1, 0, 1, 3, 0],
            "away_goals": [0, 1, 0, 0, 1, 2],
        }
    )
    model = DixonColesBTTS().fit(train)
    probabilities = model.predict_probability(train[["lambda_home", "lambda_away"]])
    assert probabilities.between(0.0, 1.0).all()
    assert len(probabilities) == len(train)


def test_dixon_coles_rejects_missing_labels() -> None:
    with pytest.raises(ValueError, match="missing Dixon-Coles"):
        DixonColesBTTS().fit(pd.DataFrame({"lambda_home": [1.0], "lambda_away": [1.0]}))
