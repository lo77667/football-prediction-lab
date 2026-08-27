import json
from datetime import UTC, datetime

import pytest

from football_prediction_lab.ai import build_pre_match_request
from football_prediction_lab.source import OpenLigaDBClient

AS_OF = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _batch():
    payload = json.dumps(
        [
            {
                "matchID": 11,
                "matchDateTimeUTC": "2026-08-08T19:00:00Z",
                "team1": {"teamId": 1, "teamName": "Home"},
                "team2": {"teamId": 2, "teamName": "Away"},
                "matchIsFinished": False,
                "matchResults": [],
                "goals": [],
                "group": {"groupName": "Matchday 1", "groupOrderID": 1},
                "lastUpdateDateTime": "2026-08-01T10:00:00",
                "leagueId": 5996,
                "leagueName": "Premier League 2026/2027",
                "leagueShortcut": "pl",
                "leagueSeason": 2026,
                "location": None,
                "numberOfViewers": None,
                "timeZoneID": None,
            }
        ]
    ).encode()
    return OpenLigaDBClient(
        transport=lambda url, timeout: payload,
        min_interval_seconds=0,
    ).fetch_league_season("pl", 2026)


def test_context_is_pre_match_only() -> None:
    batch = _batch()
    request, context = build_pre_match_request(batch, batch.matches[0], as_of_utc=AS_OF)
    serialized = json.dumps(context, sort_keys=True)
    assert request.match_id == "11"
    assert "matchResults" not in serialized
    assert "goals" not in serialized
    assert context["source_response_sha256"] == batch.response_sha256


def test_context_rejects_match_that_has_started() -> None:
    batch = _batch()
    with pytest.raises(ValueError, match="upcoming"):
        build_pre_match_request(
            batch,
            batch.matches[0],
            as_of_utc=datetime(2026, 8, 8, 19, tzinfo=UTC),
        )
