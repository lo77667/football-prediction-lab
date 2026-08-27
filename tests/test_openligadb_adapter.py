import json

import pytest

from football_prediction_lab.source import (
    OpenLigaDBClient,
    OpenLigaDBNetworkDisabled,
    OpenLigaDBPayloadError,
)

MATCH = {
    "matchID": 1,
    "matchDateTime": "2026-08-21T21:00:00",
    "matchDateTimeUTC": "2026-08-21T19:00:00Z",
    "team1": {"teamId": 10, "teamName": "Arsenal"},
    "team2": {"teamId": 20, "teamName": "Manchester United"},
    "matchIsFinished": False,
    "matchResults": [],
    "goals": [],
    "group": {"groupName": "Matchday 1", "groupOrderID": 1},
    "lastUpdateDateTime": "2026-08-20T12:00:00",
    "leagueId": 5996,
    "leagueName": "Premier League 2026/2027",
    "leagueShortcut": "pl",
    "leagueSeason": 2026,
    "location": None,
    "numberOfViewers": None,
    "timeZoneID": None,
}


def test_network_is_disabled_by_default() -> None:
    with pytest.raises(OpenLigaDBNetworkDisabled):
        OpenLigaDBClient(min_interval_seconds=0).fetch_league_season("pl", 2026)


def test_fixture_is_parsed_and_cached_without_network() -> None:
    calls: list[str] = []
    payload = json.dumps([MATCH]).encode()

    def transport(url: str, timeout: float) -> bytes:
        del timeout
        calls.append(url)
        return payload

    client = OpenLigaDBClient(transport=transport, min_interval_seconds=0)
    first = client.fetch_league_season("pl", 2026)
    second = client.fetch_league_season("pl", 2026)

    assert len(first.matches) == 1
    assert first.matches[0].kickoff_utc.isoformat() == "2026-08-21T19:00:00+00:00"
    assert first.matches[0].team1.name == "Arsenal"
    assert first.from_cache is False
    assert second.from_cache is True
    assert calls == ["https://api.openligadb.de/getmatchdata/pl/2026"]


def test_cache_ttl_zero_forces_a_fresh_fetch() -> None:
    calls: list[str] = []
    payload = json.dumps([MATCH]).encode()

    def transport(url: str, timeout: float) -> bytes:
        del timeout
        calls.append(url)
        return payload

    client = OpenLigaDBClient(
        transport=transport,
        min_interval_seconds=0,
        cache_ttl_seconds=0,
    )
    client.fetch_league_season("pl", 2026)
    second = client.fetch_league_season("pl", 2026)

    assert second.from_cache is False
    assert calls == [
        "https://api.openligadb.de/getmatchdata/pl/2026",
        "https://api.openligadb.de/getmatchdata/pl/2026",
    ]


def test_unknown_match_fields_are_rejected() -> None:
    payload = dict(MATCH, unexpected="value")
    client = OpenLigaDBClient(
        transport=lambda url, timeout: json.dumps([payload]).encode(),
        min_interval_seconds=0,
    )
    with pytest.raises(OpenLigaDBPayloadError, match="unexpected fields"):
        client.fetch_league_season("pl", 2026)


def test_non_utc_provider_timestamp_is_rejected() -> None:
    payload = dict(MATCH, matchDateTimeUTC="2026-08-21T19:00:00")
    client = OpenLigaDBClient(
        transport=lambda url, timeout: json.dumps([payload]).encode(),
        min_interval_seconds=0,
    )
    with pytest.raises(OpenLigaDBPayloadError, match="explicit UTC"):
        client.fetch_league_season("pl", 2026)


def test_path_injection_is_rejected() -> None:
    client = OpenLigaDBClient(transport=lambda url, timeout: b"[]", min_interval_seconds=0)
    with pytest.raises(ValueError, match="alphanumeric"):
        client.fetch_league_season("pl/2026", 2026)
