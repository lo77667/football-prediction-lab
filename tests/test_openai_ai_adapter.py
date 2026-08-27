import json
from datetime import UTC, datetime

import pytest

from football_prediction_lab.ai import (
    AIAnalysisError,
    AnalysisEvidence,
    AnalysisRequest,
    OpenAIJSONAnalyzer,
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


def _provider_response() -> bytes:
    output = {
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
    return json.dumps(
        {"choices": [{"message": {"content": json.dumps(output)}}]}
    ).encode()


def test_adapter_returns_verified_output_without_network() -> None:
    calls: list[dict[str, object]] = []

    def transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        return _provider_response()

    analyzer = OpenAIJSONAnalyzer(
        api_base="https://example.invalid/v1",
        api_key="fixture-only",
        transport=transport,
    )
    result = analyzer.analyze(
        _request(),
        context={"team1": "Arsenal", "team2": "Manchester United"},
    )

    assert result.status == "supported"
    assert calls[0]["url"] == "https://example.invalid/v1/chat/completions"
    assert calls[0]["body"]["response_format"]["json_schema"]["strict"] is True
    assert (
        calls[0]["body"]["response_format"]["json_schema"]["schema"]["additionalProperties"]
        is False
    )


def test_adapter_rejects_post_match_context_before_transport() -> None:
    called = False

    def transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        nonlocal called
        called = True
        return _provider_response()

    analyzer = OpenAIJSONAnalyzer(
        api_base="https://example.invalid/v1",
        api_key="fixture-only",
        transport=transport,
    )
    with pytest.raises(AIAnalysisError, match="post-match"):
        analyzer.analyze(_request(), context={"matchResults": []})
    assert called is False


def test_adapter_requires_credentials_when_called() -> None:
    analyzer = OpenAIJSONAnalyzer(
        api_base="https://example.invalid/v1",
        api_key="",
        transport=lambda *args: b"",
    )
    with pytest.raises(AIAnalysisError, match="credentials"):
        analyzer.analyze(_request(), context={"fixture": "present"})
