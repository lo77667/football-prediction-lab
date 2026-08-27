import json
from pathlib import Path

from football_prediction_lab.ai import audit_ai_store
from football_prediction_lab.storage import SQLiteStore

NOW = "2026-08-01T12:00:00+00:00"


def _output() -> dict[str, object]:
    return {
        "schema_version": "ai-analysis-v1",
        "match_id": "match-001",
        "as_of_utc": NOW,
        "status": "insufficient_evidence",
        "signals": [],
        "missing_information": ["lineup"],
        "unsupported_claims": [],
        "limitations": ["shadow only"],
    }


def _store_with_source(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.record_source_manifest("a" * 64, "OpenLigaDB", "pl-2026", "shadow_only")
    store.record_shadow_fixture(
        fixture_key="openligadb:pl:2026:1",
        match_id="match-001",
        league_shortcut="pl",
        league_season=2026,
        kickoff_utc="2026-08-08T19:00:00Z",
        team1_id=1,
        team1_name="Home",
        team2_id=2,
        team2_name="Away",
        source_manifest_fingerprint="a" * 64,
        observed_at_utc=NOW,
    )
    return store


def test_ai_audit_passes_verified_insufficient_evidence_record(tmp_path: Path) -> None:
    store = _store_with_source(tmp_path)
    store.record_ai_analysis(
        analysis_id="analysis-001",
        match_id="match-001",
        as_of_utc=NOW,
        model_name="gpt-5-mini",
        schema_version="ai-analysis-v1",
        status="insufficient_evidence",
        output=_output(),
        source_manifest_fingerprint="a" * 64,
        created_at_utc=NOW,
    )
    report = audit_ai_store(store)
    assert report["status"] == "passed"
    assert all(report["checks"].values())


def test_ai_audit_fails_when_source_or_fixture_is_missing(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.record_ai_analysis(
        analysis_id="analysis-001",
        match_id="missing-match",
        as_of_utc=NOW,
        model_name="gpt-5-mini",
        schema_version="ai-analysis-v1",
        status="insufficient_evidence",
        output={**_output(), "match_id": "missing-match"},
        source_manifest_fingerprint="b" * 64,
        created_at_utc=NOW,
    )
    report = audit_ai_store(store)
    assert report["status"] == "failed"
    assert report["checks"]["all_analysis_sources_exist"] is False
    assert report["checks"]["all_analysis_cutoffs_precede_kickoff"] is False


def test_ai_audit_rejects_forbidden_output_json(tmp_path: Path) -> None:
    store = _store_with_source(tmp_path)
    with store.transaction() as connection:
        connection.execute(
            "INSERT INTO ai_analyses("
            "analysis_id, match_id, as_of_utc, model_name, schema_version, status, "
            "output_json, source_manifest_fingerprint, created_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "analysis-unsafe",
                "match-001",
                NOW,
                "gpt-5-mini",
                "ai-analysis-v1",
                "supported",
                json.dumps({**_output(), "odds": {}}),
                "a" * 64,
                NOW,
            ),
        )
    report = audit_ai_store(store)
    assert report["status"] == "failed"
    assert report["checks"]["no_forbidden_output_fields"] is False
