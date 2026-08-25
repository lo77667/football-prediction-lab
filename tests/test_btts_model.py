import pandas as pd
import pytest

from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split


def _frame(rows: int = 20) -> pd.DataFrame:
    values = []
    for index in range(rows):
        values.append(
            {
                "match_id": f"m{index:03d}",
                "kickoff_utc": pd.Timestamp("2024-01-01", tz="UTC")
                + pd.Timedelta(value=index, unit="D"),
                "btts": index % 2,
                "home_avg_scored": float(index % 4),
                "home_avg_conceded": float((index + 1) % 3),
                "home_btts_rate": float(index % 5) / 5,
                "away_avg_scored": float((index + 2) % 4),
                "away_avg_conceded": float((index + 3) % 3),
                "away_btts_rate": float((index + 1) % 5) / 5,
                "home_matches_before": min(index, 5),
                "away_matches_before": min(index, 5),
            }
        )
    return pd.DataFrame(values)


def test_temporal_split_preserves_order() -> None:
    split = temporal_split(_frame(), train_fraction=0.6, validation_fraction=0.2)
    assert split.train["match_id"].tolist() == [f"m{index:03d}" for index in range(12)]
    assert split.validation["match_id"].tolist() == [f"m{index:03d}" for index in range(12, 16)]
    assert split.test["match_id"].tolist() == [f"m{index:03d}" for index in range(16, 20)]


def test_model_returns_bounded_probabilities() -> None:
    frame = _frame()
    model = BttsLogisticBaseline().fit(frame.iloc[:15])
    probabilities = model.predict_probability(frame.iloc[15:])
    assert len(probabilities) == 5
    assert ((probabilities >= 0) & (probabilities <= 1)).all()


def test_model_rejects_single_class_training_data() -> None:
    frame = _frame().assign(btts=1)
    with pytest.raises(ValueError, match="both BTTS classes"):
        BttsLogisticBaseline().fit(frame)
