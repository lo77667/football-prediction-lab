import json
from datetime import UTC

import pytest

from football_prediction_lab.source.worldcup2026 import (
    WorldCup2026Client,
    WorldCup2026NetworkDisabled,
    WorldCup2026PayloadError,
)


def payload() -> bytes:
    return json.dumps(
        {
            "version": "test-v1",
            "count": 1,
            "matches": [
                {
                    "id": 1,
                    "stage": "group",
                    "stageName": "Group A",
                    "group": "A",
                    "venue": "Test Stadium",
                    "kickoff": {"utc": "2026-06-11T19:00:00.000Z"},
                    "home": {"code": "MEX", "name": "Mexico"},
                    "away": {"code": "RSA", "name": "South Africa"},
                    "attributionSnippets": {
                        "text": "Mexico vs South Africa: https://example.com/match/1"
                    },
                }
            ],
        }
    ).encode()


def test_worldcup_adapter_parses_and_caches_fixture() -> None:
    calls: list[str] = []

    def transport(url: str, timeout: float) -> bytes:
        calls.append(url)
        return payload()

    client = WorldCup2026Client(transport=transport, cache_ttl_seconds=30)
    first = client.fetch_fixtures()
    second = client.fetch_fixtures()
    assert len(first.fixtures) == 1
    assert first.fixtures[0].kickoff_utc.tzinfo == UTC
    assert first.fixtures[0].home.code == "MEX"
    assert first.from_cache is False
    assert second.from_cache is True
    assert len(calls) == 1
    assert first.response_sha256 == second.response_sha256


def test_worldcup_adapter_requires_explicit_network_opt_in() -> None:
    with pytest.raises(WorldCup2026NetworkDisabled):
        WorldCup2026Client().fetch_fixtures()


def test_worldcup_adapter_rejects_bad_count_and_bad_payload() -> None:
    def bad_count(_: str, __: float) -> bytes:
        value = json.loads(payload())
        value["count"] = 2
        return json.dumps(value).encode()

    with pytest.raises(WorldCup2026PayloadError, match="count"):
        WorldCup2026Client(transport=bad_count).fetch_fixtures()

    with pytest.raises(ValueError, match="timezone"):
        WorldCup2026Client(transport=lambda _url, _timeout: payload()).fetch_fixtures("")
