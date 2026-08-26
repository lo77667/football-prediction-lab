from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from football_prediction_lab.storage import SCHEMA_VERSION, SQLiteStore

NOW = "2025-01-01T12:00:00+00:00"


def _prediction(prediction_id: str = "pred-001") -> dict[str, object]:
    return {
        "prediction_id": prediction_id,
        "match_id": "match-001",
        "market": "btts",
        "as_of_utc": NOW,
        "kickoff_utc": "2025-01-02T15:00:00+00:00",
        "model_version": "model-v1",
        "policy_version": "policy-v1",
        "feature_version": "feature-v1",
        "probability": 0.62,
        "source_manifest_fingerprint": "a" * 64,
    }


def test_schema_migration_and_integrity_are_deterministic(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    result = store.integrity_check()
    assert result == {
        "integrity_check": "ok",
        "foreign_key_errors": 0,
        "schema_version": SCHEMA_VERSION,
        "passed": True,
    }
    with store.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {
        "ingestion_runs",
        "source_manifests",
        "predictions",
        "shadow_runs",
        "notifications",
        "notification_attempts",
        "failures",
        "health_snapshots",
        "model_policy_versions",
        "audit_events",
    }.issubset(tables)


def test_transaction_rolls_back_on_failure(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(RuntimeError):
        with store.transaction() as connection:
            connection.execute(
                "INSERT INTO ingestion_runs("
                "run_id, source_version, started_at_utc, status) VALUES (?, ?, ?, ?)",
                ("run-1", "v1", NOW, "started"),
            )
            raise RuntimeError("rollback")
    assert store.metrics()["ingestion_runs"] == 0


def test_predictions_and_notifications_are_idempotent(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    assert store.record_prediction(_prediction()) is True
    assert store.record_prediction(_prediction()) is False
    assert store.record_notification("n-1", "pred-001", "sent", NOW) is True
    assert store.record_notification("n-1", "pred-001", "sent", NOW) is False
    assert store.record_notification("n-2", "pred-001", "sent", NOW) is False
    assert store.metrics()["predictions"] == 1
    assert store.metrics()["notifications"] == 1


def test_all_operational_entities_and_metrics_are_recorded(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.record_ingestion_run("run-1", "source-v1", NOW, "completed", 10, 1)
    assert store.record_source_manifest("a" * 64, "fixture", "v1", "test-only") is True
    assert store.record_shadow_run("shadow-1", NOW, "completed") is True
    assert (
        store.record_model_policy_version("v1", "model-v1", "policy-v1", "feature-v1", NOW) is True
    )
    store.record_prediction(_prediction())
    store.record_notification("n-1", "pred-001", "sent", NOW)
    store.record_notification_attempt("n-1", 1, "sent", NOW)
    store.record_failure("source", "run-1", "timeout", "open", NOW)
    store.record_health(NOW, "healthy", 0.1)
    store.record_audit("test", "run-1", NOW, {"status": "ok"})
    metrics = store.metrics()
    assert all(metrics[table] == 1 for table in metrics)
    assert store.integrity_check()["passed"] is True


def test_audit_rejects_sensitive_top_level_fields(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError, match="sensitive"):
        store.record_audit("unsafe", None, NOW, {"authorization": "Bearer secret"})
    with pytest.raises(ValueError, match="sensitive"):
        store.record_audit("unsafe", None, NOW, {"nested": [{"secret": "hidden"}]})
    assert store.metrics()["audit_events"] == 0


def test_backup_and_restore_are_integrity_checked_and_atomic(tmp_path: Path) -> None:
    source = SQLiteStore(tmp_path / "source.sqlite3")
    source.record_prediction(_prediction())
    backup = tmp_path / "backups" / "source.sqlite3"
    source.backup_to(backup)
    assert backup.is_file()
    restored_path = tmp_path / "restored" / "state.sqlite3"
    SQLiteStore.restore_from(backup, restored_path)
    restored = SQLiteStore(restored_path)
    assert restored.metrics()["predictions"] == 1
    assert restored.integrity_check()["passed"] is True
    assert not list(backup.parent.glob("*.tmp"))


def test_corrupt_backup_is_rejected_without_overwriting_destination(tmp_path: Path) -> None:
    backup = tmp_path / "bad.sqlite3"
    backup.write_bytes(b"not a sqlite database")
    destination = tmp_path / "destination.sqlite3"
    destination.write_bytes(b"original")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        SQLiteStore.restore_from(backup, destination)
    assert destination.read_bytes() == b"original"


def test_backup_bytes_are_replayable(tmp_path: Path) -> None:
    source = SQLiteStore(tmp_path / "source.sqlite3")
    source.record_prediction(_prediction())
    first = tmp_path / "first.sqlite3"
    second = tmp_path / "second.sqlite3"
    source.backup_to(first)
    source.backup_to(second)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(json.dumps(source.metrics()))["predictions"] == 1
