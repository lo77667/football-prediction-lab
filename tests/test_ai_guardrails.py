from datetime import UTC, datetime

import pytest

from football_prediction_lab.ai import (
    AIAnalysisError,
    AnalysisEvidence,
    AnalysisRequest,
    validate_ai_output,
)

AS_OF = datetime(2026, 8, 1, 12, tzinfo=UTC)
KICKOFF = datetime(2026, 8, 8, 19, tzinfo=UTC)


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        match_id="match-001",
        kickoff_utc=KICKOFF,
        as_of_utc=AS_OF,
        evidence=(
            AnalysisEvidence(
                evidence_id="fixture-001",
                source_name="OpenLigaDB",
                source_url="https://api.openligadb.de/getmatchdata/pl/2026",
                captured_at_utc=AS_OF,
                content_sha256="a" * 64,
            ),
        ),
    )


def _output(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "ai-analysis-v1",
        "match_id": "match-001",
        "as_of_utc": AS_OF.isoformat(),
        "status": "supported",
        "signals": [
            {
                "name": "fixture_available",
                "value": "fixture is present before kickoff",
                "evidence_ids": ["fixture-001"],
            }
        ],
        "missing_information": [],
        "unsupported_claims": [],
        "limitations": ["not a prediction"],
    }
    payload.update(changes)
    return payload


def test_supported_output_requires_supplied_evidence() -> None:
    result = validate_ai_output(_output(), _request())
    assert result.match_id == "match-001"
    assert result.signals[0].evidence_ids == ("fixture-001",)


def test_unknown_evidence_is_rejected() -> None:
    payload = _output(
        signals=[{"name": "injury", "value": "unknown", "evidence_ids": ["invented"]}]
    )
    with pytest.raises(AIAnalysisError, match="evidence"):
        validate_ai_output(payload, _request())


def test_unsupported_claims_are_rejected() -> None:
    with pytest.raises(AIAnalysisError, match="unsupported claims"):
        validate_ai_output(_output(unsupported_claims=["team will win"]), _request())


def test_result_and_financial_fields_are_rejected() -> None:
    with pytest.raises(AIAnalysisError, match="forbidden"):
        validate_ai_output(_output(result="1-0"), _request())
    with pytest.raises(AIAnalysisError, match="forbidden"):
        validate_ai_output(_output(odds={"home": 2.0}), _request())


def test_cutoff_must_precede_kickoff() -> None:
    request = AnalysisRequest(
        match_id="match-001",
        kickoff_utc=AS_OF,
        as_of_utc=KICKOFF,
        evidence=(),
    )
    with pytest.raises(AIAnalysisError, match="cutoff"):
        validate_ai_output(_output(status="insufficient_evidence"), request)


def test_insufficient_evidence_is_valid_without_signals() -> None:
    result = validate_ai_output(
        _output(status="insufficient_evidence", signals=[], missing_information=["lineup"]),
        _request(),
    )
    assert result.status == "insufficient_evidence"
    assert result.signals == ()
