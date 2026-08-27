import json
from pathlib import Path

import pytest

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


def test_ai_analysis_is_stored_idempotently_without_raw_provider_data(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    assert (
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
        is True
    )
    assert (
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
        is False
    )
    assert store.ai_analysis_count() == 1
    with store.connect() as connection:
        row = connection.execute("SELECT output_json FROM ai_analyses").fetchone()
    assert row is not None
    assert json.loads(row[0])["status"] == "insufficient_evidence"
    assert "matchResults" not in row[0]


def test_ai_analysis_storage_rejects_forbidden_fields(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError, match="sensitive"):
        store.record_ai_analysis(
            analysis_id="analysis-unsafe",
            match_id="match-001",
            as_of_utc=NOW,
            model_name="gpt-5-mini",
            schema_version="ai-analysis-v1",
            status="supported",
            output={**_output(), "odds": {}},
            source_manifest_fingerprint="a" * 64,
            created_at_utc=NOW,
        )
