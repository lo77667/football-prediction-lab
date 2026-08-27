import json
from datetime import date
from pathlib import Path

import pytest

from football_prediction_lab.source import (
    FootballDataClient,
    ProviderAuthenticationRequired,
    ProviderNetworkDisabled,
    ProviderPayloadError,
    SportScoreClient,
    TheSportsDBClient,
    build_enabled_clients,
)

SPORTSCORE_PAYLOAD = {
    "sport": "football",
    "count": 1,
    "matches": [
        {
            "home": "Arsenal",
            "away": "Manchester United",
            "home_score": None,
            "away_score": None,
            "status": "upcoming",
            "status_text": "Tomorrow",
            "time": "2026-08-28T19:00:00Z",
            "slug": "arsenal-vs-manchester-united-1",
        }
    ],
}

FOOTBALL_DATA_PAYLOAD = {
    "count": 1,
    "matches": [
        {
            "id": 42,
            "utcDate": "2026-08-28T19:00:00Z",
            "status": "SCHEDULED",
            "homeTeam": {"name": "Arsenal"},
            "awayTeam": {"name": "Manchester United"},
            "score": {"fullTime": {"home": None, "away": None}},
        }
    ],
}

THESPORTSDB_PAYLOAD = {
    "events": [
        {
            "idEvent": "99",
            "strTimestamp": "2026-08-28T19:00:00+00:00",
            "strHomeTeam": "Arsenal",
            "strAwayTeam": "Manchester United",
            "strStatus": "Not Started",
            "intHomeScore": None,
            "intAwayScore": None,
        }
    ]
}


def encoded(value: dict) -> bytes:
    return json.dumps(value).encode("utf-8")


def test_sportscore_network_is_disabled_by_default() -> None:
    with pytest.raises(ProviderNetworkDisabled):
        SportScoreClient().fetch_fixtures(date(2026, 8, 28))


def test_sportscore_accepts_numeric_score_strings() -> None:
    payload = json.loads(json.dumps(SPORTSCORE_PAYLOAD))
    payload["matches"][0]["home_score"] = "0"
    payload["matches"][0]["away_score"] = "1"
    client = SportScoreClient(transport=lambda url, headers, timeout: encoded(payload))
    batch = client.fetch_fixtures("2026-08-28")
    assert batch.matches[0].home_score == 0
    assert batch.matches[0].away_score == 1


def test_sportscore_fixture_contract_and_query() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        del timeout
        calls.append((url, headers))
        return encoded(SPORTSCORE_PAYLOAD)

    batch = SportScoreClient(transport=transport).fetch_fixtures(
        "2026-08-28", competition="premier-league"
    )
    assert batch.provider == "SportScore"
    assert batch.matches[0].home_team == "Arsenal"
    assert batch.matches[0].kickoff_utc.isoformat() == "2026-08-28T19:00:00+00:00"
    assert "competition=premier-league" in calls[0][0]
    assert "sport=football" in calls[0][0]


def test_football_data_requires_token_before_request() -> None:
    with pytest.raises(ProviderAuthenticationRequired):
        FootballDataClient(transport=lambda url, headers, timeout: b"{}").fetch_fixtures(
            date(2026, 8, 28)
        )


def test_football_data_fixture_contract_and_auth_header() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        del timeout
        calls.append((url, headers))
        return encoded(FOOTBALL_DATA_PAYLOAD)

    batch = FootballDataClient(token="secret-token", transport=transport).fetch_fixtures(
        "2026-08-28", competition="PL"
    )
    assert batch.provider == "football-data.org"
    assert batch.matches[0].external_id == "42"
    assert calls[0][1]["X-Auth-Token"] == "secret-token"
    assert "competitions=PL" in calls[0][0]


def test_thesportsdb_key_is_redacted_from_batch_endpoint() -> None:
    secret = "free-test-key"

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        del headers, timeout
        assert secret in url
        return encoded(THESPORTSDB_PAYLOAD)

    batch = TheSportsDBClient(token=secret, transport=transport).fetch_fixtures(
        date(2026, 8, 28)
    )
    assert secret not in batch.endpoint
    assert "<redacted>" in batch.endpoint
    assert batch.matches[0].external_id == "99"


def test_provider_payload_schema_is_rejected() -> None:
    client = SportScoreClient(transport=lambda url, headers, timeout: encoded({}))
    with pytest.raises(ProviderPayloadError, match="matches list"):
        client.fetch_fixtures("2026-08-28")


def test_registry_enables_four_adapters_without_network_or_secrets() -> None:
    root = Path(__file__).resolve().parents[1]
    clients = build_enabled_clients(root / "configs" / "external_sources.yaml")
    assert set(clients) == {"openligadb", "sportscore", "football_data", "thesportsdb"}
    assert clients["sportscore"].allow_network is False
    assert clients["football_data"].token is None
    assert clients["thesportsdb"].token is None
