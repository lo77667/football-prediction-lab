from datetime import UTC, datetime, timedelta

import pytest

from football_prediction_lab.nqbe_api import NQBEAPI, NQBEResearchLedger

KICKOFF = datetime(2026, 8, 31, 20, tzinfo=UTC)


def request() -> dict[str, object]:
    return {
        "match_id": "api-fixture",
        "captured_at": (KICKOFF - timedelta(minutes=30)).isoformat(),
        "kickoff_at": KICKOFF.isoformat(),
        "odds_history": [2.1, 2.0, 1.9],
        "home_rate": 1.3,
        "away_rate": 1.0,
    }


def test_api_returns_json_safe_research_response(tmp_path) -> None:
    response = NQBEAPI().post_analysis(request())
    assert response["ok"] is True
    assert response["research_only"] is True
    assert response["result"]["captured_at"] == (KICKOFF - timedelta(minutes=30)).isoformat()

    ledger = NQBEResearchLedger(tmp_path / "ledger.jsonl")
    ledger.append(response)
    assert ledger.read() == [response]


def test_api_rejects_missing_fields_and_ledger_rejects_non_research() -> None:
    with pytest.raises(ValueError, match="missing"):
        NQBEAPI().post_analysis({})
    with pytest.raises(ValueError, match="only research-only"):
        NQBEResearchLedger(__import__("pathlib").Path("/tmp/nqbe-test-ledger.jsonl")).append(
            {"research_only": False}
        )
