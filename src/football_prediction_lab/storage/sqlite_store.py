"""Persistent local operational storage for Cycle 45."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    source_version TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS source_manifests (
    manifest_fingerprint TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    input_sha256 TEXT,
    captured_at_utc TEXT,
    usage_policy TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_fixtures (
    fixture_key TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    league_shortcut TEXT NOT NULL,
    league_season INTEGER NOT NULL,
    kickoff_utc TEXT NOT NULL,
    team1_id INTEGER NOT NULL,
    team1_name TEXT NOT NULL,
    team2_id INTEGER NOT NULL,
    team2_name TEXT NOT NULL,
    source_manifest_fingerprint TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'upcoming')
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    market TEXT NOT NULL,
    as_of_utc TEXT NOT NULL,
    kickoff_utc TEXT NOT NULL,
    model_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    probability REAL NOT NULL CHECK(probability >= 0 AND probability <= 1),
    source_manifest_fingerprint TEXT,
    UNIQUE(match_id, market, as_of_utc, policy_version)
);
CREATE TABLE IF NOT EXISTS shadow_runs (
    run_id TEXT PRIMARY KEY,
    as_of_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    predictions_issued INTEGER NOT NULL DEFAULT 0,
    predictions_skipped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(prediction_id)
);
CREATE TABLE IF NOT EXISTS notification_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempted_at_utc TEXT NOT NULL,
    error_code TEXT,
    retryable INTEGER NOT NULL DEFAULT 0,
    UNIQUE(notification_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS failures (
    failure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    reference_id TEXT,
    error_code TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    heartbeat_age_seconds REAL,
    storage_integrity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_policy_versions (
    version_key TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    reference_id TEXT,
    created_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def _sensitive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {
            key for child in value.values() for key in _sensitive_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _sensitive_keys(child)}
    return set()


def _safe_json(value: dict[str, Any]) -> str:
    forbidden = {
        "token",
        "bot_token",
        "authorization",
        "password",
        "secret",
        "raw_data",
        "target",
        "result",
        "odds",
        "roi",
        "ev",
        "stake",
    }
    if forbidden.intersection(_sensitive_keys(value)):
        raise ValueError("sensitive fields are not allowed in audit payload")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SQLiteStore:
    """Single-process SQLite repository with explicit transactions and integrity checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at_utc) "
                "VALUES (?, datetime('now'))",
                (SCHEMA_VERSION,),
            )
            connection.commit()

    def integrity_check(self) -> dict[str, Any]:
        with self.connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        return {
            "integrity_check": result,
            "foreign_key_errors": len(foreign_keys),
            "schema_version": version,
            "passed": result == "ok" and not foreign_keys and version == SCHEMA_VERSION,
        }

    def record_ingestion_run(
        self,
        run_id: str,
        source_version: str,
        started_at_utc: str,
        status: str,
        accepted_rows: int = 0,
        rejected_rows: int = 0,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO ingestion_runs("
                "run_id, source_version, started_at_utc, status, accepted_rows, rejected_rows) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, source_version, started_at_utc, status, accepted_rows, rejected_rows),
            )

    def record_source_manifest(
        self,
        manifest_fingerprint: str,
        source_name: str,
        source_version: str,
        usage_policy: str,
        input_sha256: str | None = None,
        captured_at_utc: str | None = None,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO source_manifests("
                "manifest_fingerprint, source_name, source_version, input_sha256, "
                "captured_at_utc, usage_policy) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    manifest_fingerprint,
                    source_name,
                    source_version,
                    input_sha256,
                    captured_at_utc,
                    usage_policy,
                ),
            )
        return cursor.rowcount == 1

    def record_shadow_fixture(
        self,
        fixture_key: str,
        match_id: str,
        league_shortcut: str,
        league_season: int,
        kickoff_utc: str,
        team1_id: int,
        team1_name: str,
        team2_id: int,
        team2_name: str,
        source_manifest_fingerprint: str,
        observed_at_utc: str,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO shadow_fixtures("
                "fixture_key, match_id, league_shortcut, league_season, kickoff_utc, "
                "team1_id, team1_name, team2_id, team2_name, source_manifest_fingerprint, "
                "first_seen_at_utc, last_seen_at_utc, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fixture_key,
                    match_id,
                    league_shortcut,
                    league_season,
                    kickoff_utc,
                    team1_id,
                    team1_name,
                    team2_id,
                    team2_name,
                    source_manifest_fingerprint,
                    observed_at_utc,
                    observed_at_utc,
                    "upcoming",
                ),
            )
            if cursor.rowcount == 1:
                return True
            connection.execute(
                "UPDATE shadow_fixtures SET last_seen_at_utc=?, "
                "source_manifest_fingerprint=? WHERE fixture_key=?",
                (observed_at_utc, source_manifest_fingerprint, fixture_key),
            )
        return False

    def shadow_fixture_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM shadow_fixtures").fetchone()[0])

    def record_shadow_run(
        self,
        run_id: str,
        as_of_utc: str,
        status: str,
        predictions_issued: int = 0,
        predictions_skipped: int = 0,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO shadow_runs("
                "run_id, as_of_utc, status, predictions_issued, predictions_skipped) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, as_of_utc, status, predictions_issued, predictions_skipped),
            )
        return cursor.rowcount == 1

    def record_model_policy_version(
        self,
        version_key: str,
        model_version: str,
        policy_version: str,
        feature_version: str,
        recorded_at_utc: str,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO model_policy_versions("
                "version_key, model_version, policy_version, feature_version, recorded_at_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (version_key, model_version, policy_version, feature_version, recorded_at_utc),
            )
        return cursor.rowcount == 1

    def record_prediction(self, prediction: dict[str, Any]) -> bool:
        columns = (
            "prediction_id",
            "match_id",
            "market",
            "as_of_utc",
            "kickoff_utc",
            "model_version",
            "policy_version",
            "feature_version",
            "probability",
            "source_manifest_fingerprint",
        )
        values = tuple(prediction.get(column) for column in columns)
        with self.transaction() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO predictions({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
        return cursor.rowcount == 1

    def record_notification(
        self, notification_id: str, prediction_id: str, status: str, created_at_utc: str
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO notifications("
                "notification_id, prediction_id, status, created_at_utc) "
                "VALUES (?, ?, ?, ?)",
                (notification_id, prediction_id, status, created_at_utc),
            )
        return cursor.rowcount == 1

    def record_notification_attempt(
        self,
        notification_id: str,
        attempt_number: int,
        status: str,
        attempted_at_utc: str,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO notification_attempts("
                "notification_id, attempt_number, status, attempted_at_utc, error_code, retryable) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    notification_id,
                    attempt_number,
                    status,
                    attempted_at_utc,
                    error_code,
                    int(retryable),
                ),
            )
        return cursor.rowcount == 1

    def record_failure(
        self,
        component: str,
        reference_id: str | None,
        error_code: str,
        status: str,
        created_at_utc: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO failures("
                "component, reference_id, error_code, status, created_at_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (component, reference_id, error_code, status, created_at_utc),
            )

    def record_health(
        self, captured_at_utc: str, status: str, heartbeat_age_seconds: float | None = None
    ) -> None:
        integrity = self.integrity_check()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO health_snapshots("
                "captured_at_utc, status, heartbeat_age_seconds, storage_integrity) "
                "VALUES (?, ?, ?, ?)",
                (
                    captured_at_utc,
                    status,
                    heartbeat_age_seconds,
                    "passed" if integrity["passed"] else "failed",
                ),
            )

    def record_audit(
        self,
        event_type: str,
        reference_id: str | None,
        created_at_utc: str,
        payload: dict[str, Any],
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO audit_events("
                "event_type, reference_id, created_at_utc, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (event_type, reference_id, created_at_utc, _safe_json(payload)),
            )

    def metrics(self) -> dict[str, int]:
        tables = (
            "ingestion_runs",
            "source_manifests",
            "predictions",
            "shadow_runs",
            "notifications",
            "notification_attempts",
            "failures",
            "health_snapshots",
            "audit_events",
        )
        with self.connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

    def backup_to(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        source_connection = self.connect()
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        os.replace(temporary, destination)
        if not SQLiteStore(destination).integrity_check()["passed"]:
            raise ValueError("backup integrity check failed")

    @staticmethod
    def restore_from(backup: Path, destination: Path) -> None:
        if not backup.is_file():
            raise FileNotFoundError("backup file is missing")
        with tempfile.TemporaryDirectory(prefix="cycle45-restore-") as temporary_dir:
            temporary_path = Path(temporary_dir) / "restored.sqlite3"
            shutil.copyfile(backup, temporary_path)
            restored = SQLiteStore(temporary_path)
            if not restored.integrity_check()["passed"]:
                raise ValueError("backup failed integrity validation")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary_path, destination)
