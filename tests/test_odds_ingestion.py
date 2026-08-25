import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from football_prediction_lab.evaluation.odds_ingestion import ingest_jsonl_snapshots
from football_prediction_lab.evaluation.odds_schema import MatchReference

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)


def payload(match_id: str = "m-1") -> dict[str, object]:
    return {
        "snapshot_id": "s-1",
        "match_id": match_id,
        "match_kickoff_utc": KICKOFF.isoformat(),
        "market": "btts",
        "market_definition": "Both teams to score at least one goal",
        "selection": "yes",
        "decimal_odds": 2.0,
        "captured_at": (KICKOFF - timedelta(hours=1)).isoformat(),
        "provenance_id": "p-1",
        "odds_type": "pre_match",
        "is_licensed_or_reusable": True,
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_ingestion_enriches_file_hash_and_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "snapshots.jsonl"
    manifest = tmp_path / "manifest.json"
    write_jsonl(source, [payload()])
    accepted, result = ingest_jsonl_snapshots(
        source,
        source_name="fixture-source",
        source_version="v1",
        license_status="test-only",
        reusable=True,
        matches=[MatchReference(match_id="m-1", kickoff_utc=KICKOFF, season="2425")],
        manifest_path=manifest,
    )
    assert len(accepted) == 1
    assert accepted[0].input_sha256 == result.input_sha256
    assert result.rows_valid == 1
    assert result.quality_duplicate_identity_rows == 0
    assert len(result.quality_profile_sha256) == 64
    assert result.quality_non_monotonic_match_captures == 0
    assert manifest.exists()


def test_ingestion_rejects_non_reusable_source(tmp_path: Path) -> None:
    source = tmp_path / "snapshots.jsonl"
    write_jsonl(source, [payload()])
    accepted, result = ingest_jsonl_snapshots(
        source,
        source_name="restricted-source",
        source_version="v1",
        license_status="restricted",
        reusable=False,
        matches=[MatchReference(match_id="m-1", kickoff_utc=KICKOFF, season="2425")],
    )
    assert accepted == []
    assert result.rejected_by_reason == {"source_not_reusable": 1}


def test_ingestion_rejects_protected_holdout(tmp_path: Path) -> None:
    source = tmp_path / "snapshots.jsonl"
    write_jsonl(source, [payload(match_id="m-2526")])
    accepted, result = ingest_jsonl_snapshots(
        source,
        source_name="fixture-source",
        source_version="v1",
        license_status="test-only",
        reusable=True,
        matches=[
            MatchReference(match_id="m-2526", kickoff_utc=KICKOFF, season="2526")
        ],
    )
    assert accepted == []
    assert result.protected_holdout_rows == 1
    assert "protected_holdout_season" in result.rejected_by_reason


def test_ingestion_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest_jsonl_snapshots(
            tmp_path / "missing.jsonl",
            source_name="fixture-source",
            source_version="v1",
            license_status="test-only",
            reusable=True,
            matches=[],
        )
