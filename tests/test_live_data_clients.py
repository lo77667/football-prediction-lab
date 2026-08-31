import json

import pytest

from football_prediction_lab.source.football_data_org import (
    FootballDataOrgAuthenticationError,
    FootballDataOrgClient,
)
from football_prediction_lab.source.rss import RSSClient, RSSFetchError, parse_feed
from football_prediction_lab.source.the_odds_api import TheOddsApiClient


def test_football_data_org_sends_x_auth_token_and_preserves_payload() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        calls.append((url, headers))
        return b'{"matches": []}'

    response = FootballDataOrgClient("token-123", transport=transport).fetch_matches(
        "PL", status="FINISHED", limit=1
    )
    assert response.payload == {"matches": []}
    assert calls[0][1]["X-Auth-Token"] == "token-123"
    assert "status=FINISHED" in calls[0][0]
    assert "limit=1" in calls[0][0]


def test_football_data_org_surfaces_authentication_error() -> None:
    def rejected(_: str, __: dict[str, str], ___: float) -> bytes:
        raise FootballDataOrgAuthenticationError("HTTP 403")

    with pytest.raises(FootballDataOrgAuthenticationError):
        FootballDataOrgClient("token", transport=rejected).fetch_matches("PL")


def test_odds_client_is_read_only_and_builds_query() -> None:
    calls: list[str] = []

    def transport(url: str, _: float) -> bytes:
        calls.append(url)
        return b'[{"id":"event-1"}]'

    response = TheOddsApiClient("key", transport=transport).fetch_odds("soccer_epl")
    assert response.payload == [{"id": "event-1"}]
    assert "apiKey=key" in calls[0]
    assert "/sports/soccer_epl/odds?" in calls[0]


def test_rss_parser_normalizes_atom_and_rss_items() -> None:
    payload = (
        b"""<?xml version="1.0"?><rss><channel><item><guid>x1</guid>"""
        b"""<title>Match update</title><link>https://example.com/1</link>"""
        b"""<pubDate>Mon, 31 Aug 2026 12:00:00 GMT</pubDate>"""
        b"""<description>Summary</description></item></channel></rss>"""
    )
    batch = parse_feed("https://example.com/feed", payload)
    assert len(batch.items) == 1
    assert batch.items[0].title == "Match update"
    assert batch.items[0].published_at_utc is not None
    assert batch.items[0].published_at_utc.tzinfo is not None


def test_rss_requires_opt_in_for_network() -> None:
    with pytest.raises(RSSFetchError):
        RSSClient().fetch("https://example.com/feed")


def test_rss_rejects_invalid_xml() -> None:
    with pytest.raises(RSSFetchError):
        parse_feed("https://example.com/feed", json.dumps({"bad": True}).encode())
