from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from football_prediction_lab.contracts import MatchRecord, PredictionRecord


def test_match_record_rejects_blank_team_name() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id="m1",
            kickoff_utc=datetime(2024, 1, 1, tzinfo=UTC),
            competition="Example League",
            season="2023-24",
            home_team=" ",
            away_team="Away",
            source="test",
        )


def test_prediction_probability_is_bounded() -> None:
    with pytest.raises(ValidationError):
        PredictionRecord(
            prediction_id="p1",
            match_id="m1",
            market="btts",
            predicted_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
            model_version="v0",
            feature_version="v0",
            probability_yes=1.1,
            decision="yes",
            data_cutoff_utc=datetime(2024, 1, 1, tzinfo=UTC),
            input_fingerprint="abc",
        )


def test_prediction_contract_accepts_valid_record() -> None:
    record = PredictionRecord(
        prediction_id="p1",
        match_id="m1",
        market="btts",
        predicted_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
        model_version="v0",
        feature_version="v0",
        probability_yes=0.62,
        decision="yes",
        data_cutoff_utc=datetime(2024, 1, 1, tzinfo=UTC),
        input_fingerprint="abc",
    )
    assert record.probability_yes == 0.62
