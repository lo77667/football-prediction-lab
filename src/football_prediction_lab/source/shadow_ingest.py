"""Local, pre-match-only ingestion for OpenLigaDB shadow observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from football_prediction_lab.source.openligadb import OpenLigaDBClient, OpenLigaMatch
from football_prediction_lab.storage import SQLiteStore


@dataclass(frozen=True)
class ShadowIngestResult:
    run_id: str
    as_of_utc: str
    source_version: str
    manifest_fingerprint: str
    response_sha256: str
    fetched_at_utc: str
    total_matches: int
    finished_matches: int
    upcoming_matches: int
    inserted_fixtures: int
    repeated_fixtures: int
    database_path: str


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("as_of_utc must be explicit UTC")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _require_utc(value).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _fixture_key(match: OpenLigaMatch) -> str:
    return f"openligadb:{match.league_shortcut}:{match.league_season}:{match.match_id}"


def _manifest_fingerprint(
    *, endpoint: str, source_version: str, response_sha256: str
) -> str:
    payload = {
        "endpoint": endpoint,
        "response_sha256": response_sha256,
        "source_version": source_version,
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _run_id(*, as_of_utc: datetime, manifest_fingerprint: str) -> str:
    payload = {"as_of_utc": _iso(as_of_utc), "manifest_fingerprint": manifest_fingerprint}
    return f"openligadb-shadow-{hashlib.sha256(_canonical(payload)).hexdigest()[:40]}"


class OpenLigaDBShadowIngestor:
    """Persist only future fixture metadata; never persist provider results."""

    def __init__(
        self,
        *,
        client: OpenLigaDBClient,
        store: SQLiteStore,
        league_shortcut: str = "pl",
        season: int = 2026,
    ) -> None:
        self.client = client
        self.store = store
        self.league_shortcut = league_shortcut
        self.season = season

    def run_once(self, *, as_of_utc: datetime | None = None) -> ShadowIngestResult:
        observed_at = _require_utc(as_of_utc or datetime.now(UTC))
        batch = self.client.fetch_league_season(self.league_shortcut, self.season)
        source_version = f"openligadb:{self.league_shortcut}:{self.season}"
        manifest_fingerprint = _manifest_fingerprint(
            endpoint=batch.endpoint,
            source_version=source_version,
            response_sha256=batch.response_sha256,
        )
        run_id = _run_id(
            as_of_utc=observed_at,
            manifest_fingerprint=manifest_fingerprint,
        )
        captured_at = _iso(batch.fetched_at_utc)
        observed_iso = _iso(observed_at)
        self.store.record_source_manifest(
            manifest_fingerprint=manifest_fingerprint,
            source_name="OpenLigaDB",
            source_version=source_version,
            input_sha256=batch.response_sha256,
            captured_at_utc=captured_at,
            usage_policy="shadow_only; no commercial release",
        )
        upcoming = tuple(match for match in batch.matches if match.kickoff_utc > observed_at)
        inserted = 0
        repeated = 0
        for match in upcoming:
            if self.store.record_shadow_fixture(
                fixture_key=_fixture_key(match),
                match_id=str(match.match_id),
                league_shortcut=match.league_shortcut,
                league_season=match.league_season,
                kickoff_utc=_iso(match.kickoff_utc),
                team1_id=match.team1.team_id,
                team1_name=match.team1.name,
                team2_id=match.team2.team_id,
                team2_name=match.team2.name,
                source_manifest_fingerprint=manifest_fingerprint,
                observed_at_utc=observed_iso,
            ):
                inserted += 1
            else:
                repeated += 1
        self.store.record_ingestion_run(
            run_id=run_id,
            source_version=source_version,
            started_at_utc=observed_iso,
            status="completed",
            accepted_rows=inserted,
            rejected_rows=len(batch.matches) - len(upcoming),
        )
        self.store.record_audit(
            event_type="openligadb_shadow_ingestion",
            reference_id=run_id,
            created_at_utc=observed_iso,
            payload={
                "source_version": source_version,
                "endpoint": batch.endpoint,
                "response_sha256": batch.response_sha256,
                "manifest_fingerprint": manifest_fingerprint,
                "total_matches": len(batch.matches),
                "finished_matches": sum(match.finished for match in batch.matches),
                "upcoming_matches": len(upcoming),
                "inserted_fixtures": inserted,
                "repeated_fixtures": repeated,
                "results_persisted": False,
                "commercial_release": False,
            },
        )
        return ShadowIngestResult(
            run_id=run_id,
            as_of_utc=observed_iso,
            source_version=source_version,
            manifest_fingerprint=manifest_fingerprint,
            response_sha256=batch.response_sha256,
            fetched_at_utc=captured_at,
            total_matches=len(batch.matches),
            finished_matches=sum(match.finished for match in batch.matches),
            upcoming_matches=len(upcoming),
            inserted_fixtures=inserted,
            repeated_fixtures=repeated,
            database_path=str(self.store.path),
        )
