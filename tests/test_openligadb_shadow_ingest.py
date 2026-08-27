import json
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.source import OpenLigaDBClient, OpenLigaDBShadowIngestor
from football_prediction_lab.storage import SQLiteStore

AS_OF = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _match(match_id: int, kickoff: str, finished: bool) -> dict[str, object]:
    return {
        "matchID": match_id,
        "matchDateTimeUTC": kickoff,
        "team1": {"teamId": 10 + match_id, "teamName": f"Home {match_id}"},
        "team2": {"teamId": 20 + match_id, "teamName": f"Away {match_id}"},
        "matchIsFinished": finished,
        "matchResults": [{"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1}]
        if finished
        else [],
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


def test_ingest_filters_past_matches_and_is_idempotent(tmp_path: Path) -> None:
    payload = json.dumps(
        [
            _match(1, "2026-07-31T19:00:00Z", True),
            _match(2, "2026-08-08T19:00:00Z", False),
        ]
    ).encode()
    client = OpenLigaDBClient(
        transport=lambda url, timeout: payload,
        min_interval_seconds=0,
    )
    store = SQLiteStore(tmp_path / "shadow.sqlite3")
    ingestor = OpenLigaDBShadowIngestor(client=client, store=store)

    first = ingestor.run_once(as_of_utc=AS_OF)
    second = ingestor.run_once(as_of_utc=AS_OF)

    assert first.total_matches == 2
    assert first.finished_matches == 1
    assert first.upcoming_matches == 1
    assert first.inserted_fixtures == 1
    assert first.repeated_fixtures == 0
    assert second.inserted_fixtures == 0
    assert second.repeated_fixtures == 1
    assert store.shadow_fixture_count() == 1
    assert store.metrics()["ingestion_runs"] == 1
    with store.connect() as connection:
        row = connection.execute("SELECT payload_json FROM audit_events").fetchone()
    assert row is not None
    audit_payload = json.loads(row[0])
    assert "matchResults" not in row[0]
    assert audit_payload["results_persisted"] is False
