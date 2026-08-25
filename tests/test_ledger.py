from datetime import UTC, datetime

import pytest

from football_prediction_lab.contracts import OutcomeRecord, PredictionRecord
from football_prediction_lab.ledger.append_only import PredictionLedger


def _prediction() -> PredictionRecord:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    return PredictionRecord(
        prediction_id="p1",
        match_id="m1",
        market="btts",
        predicted_at_utc=now,
        model_version="v0",
        feature_version="f0",
        probability_yes=0.62,
        decision="yes",
        data_cutoff_utc=now,
        input_fingerprint="fingerprint",
    )


def test_ledger_requires_prediction_before_outcome(tmp_path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.jsonl")
    outcome = OutcomeRecord(
        prediction_id="p1",
        match_id="m1",
        market="btts",
        revealed_at_utc=datetime(2024, 1, 2, tzinfo=UTC),
        actual_yes=True,
        result_source="test",
    )
    with pytest.raises(ValueError, match="before its prediction"):
        ledger.append_outcome(outcome)


def test_ledger_appends_and_verifies_prediction_then_outcome(tmp_path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.jsonl")
    prediction = _prediction()
    ledger.append_prediction(prediction)
    ledger.append_outcome(
        OutcomeRecord(
            prediction_id="p1",
            match_id="m1",
            market="btts",
            revealed_at_utc=datetime(2024, 1, 2, tzinfo=UTC),
            actual_yes=True,
            result_source="test",
        )
    )
    ledger.verify()
    assert len(ledger.records()) == 2


def test_ledger_rejects_duplicate_prediction(tmp_path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.jsonl")
    ledger.append_prediction(_prediction())
    with pytest.raises(ValueError, match="already exists"):
        ledger.append_prediction(_prediction())
