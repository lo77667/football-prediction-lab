"""Independent audit checks for persisted guarded AI analyses."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from football_prediction_lab.storage import SQLiteStore

_FORBIDDEN_MARKERS = (
    "matchresults",
    '"result"',
    '"target"',
    '"odds"',
    '"ev"',
    '"roi"',
    '"stake"',
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise ValueError("stored timestamp must be explicit UTC")
    return parsed.astimezone(UTC)


def audit_ai_store(store: SQLiteStore) -> dict[str, Any]:
    """Return a fail-closed audit report without changing any stored data."""

    checks = {
        "storage_integrity": bool(store.integrity_check()["passed"]),
        "all_analysis_sources_exist": True,
        "all_analysis_cutoffs_precede_kickoff": True,
        "all_outputs_are_json": True,
        "no_forbidden_output_fields": True,
    }
    records: list[dict[str, Any]] = []
    try:
        with store.connect() as connection:
            rows = connection.execute(
                "SELECT a.analysis_id, a.match_id, a.as_of_utc, a.output_json, "
                "a.source_manifest_fingerprint, f.kickoff_utc, sm.manifest_fingerprint "
                "FROM ai_analyses a "
                "LEFT JOIN shadow_fixtures f ON f.match_id = a.match_id "
                "LEFT JOIN source_manifests sm "
                "ON sm.manifest_fingerprint = a.source_manifest_fingerprint "
                "ORDER BY a.analysis_id"
            ).fetchall()
    except Exception:
        checks["all_analysis_sources_exist"] = False
        rows = []

    for row in rows:
        output_json = str(row[3])
        try:
            json.loads(output_json)
            _utc(str(row[2]))
        except (TypeError, ValueError, json.JSONDecodeError):
            checks["all_outputs_are_json"] = False
        has_source = bool(row[4] and row[6])
        checks["all_analysis_sources_exist"] &= has_source
        cutoff_ok = False
        if row[5]:
            try:
                cutoff_ok = _utc(str(row[2])) < _utc(str(row[5]))
            except ValueError:
                cutoff_ok = False
        checks["all_analysis_cutoffs_precede_kickoff"] &= cutoff_ok
        lowered = output_json.lower()
        if any(marker in lowered for marker in _FORBIDDEN_MARKERS):
            checks["no_forbidden_output_fields"] = False
        records.append(
            {
                "analysis_id": str(row[0]),
                "match_id": str(row[1]),
                "cutoff_before_kickoff": cutoff_ok,
            }
        )
    passed = all(checks.values()) and bool(store.integrity_check()["passed"])
    return {
        "status": "passed" if passed else "failed",
        "record_count": len(records),
        "checks": checks,
        "records": records,
        "prediction_issued": False,
        "commercial_release": False,
    }
