from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from football_prediction_lab.evaluation.manual_results import (
    ManualResultLedger,
    ManualResultRecord,
)

KICKOFF = datetime(2026, 8, 8, 19, tzinfo=UTC)


def _record(**overrides: object) -> ManualResultRecord:
    payload: dict[str, object] = {
        "prediction_id": "prediction-1",
        "match_id": "match-1",
        "market": "btts",
        "kickoff_utc": KICKOFF,
        "outcome_label": "yes",
        "recorded_at_utc": datetime(2026, 8, 8, 21, tzinfo=UTC),
        "result_source": "OpenLigaDB",
        "source_snapshot_id": "snapshot-1",
    }
    payload.update(overrides)
    return ManualResultRecord.model_validate(payload)


def test_result_is_recorded_only_after_kickoff_and_is_idempotent(tmp_path) -> None:
    ledger = ManualResultLedger(tmp_path / "results.jsonl")
    record = _record()
    first_id = ledger.append(record)
    second_id = ledger.append(record)
    assert first_id == second_id
    assert len(ledger.events()) == 1
    assert ledger.events()[0]["commercial_release"] is False


def test_result_before_kickoff_is_rejected() -> None:
    with pytest.raises(ValidationError, match="before or at kickoff"):
        _record(recorded_at_utc=KICKOFF)


def test_non_utc_result_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="explicit UTC"):
        _record(recorded_at_utc="2026-08-08T22:00:00+01:00")


@pytest.mark.parametrize("field", ["odds", "roi", "ev", "stake", "token"])
def test_sensitive_terms_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        _record(**{"outcome_label": field})
