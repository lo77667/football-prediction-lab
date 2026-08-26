"""Fail-closed and portable readiness checks for authorized external sources."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from football_prediction_lab.ingestion.external_contracts import (
    ExternalSnapshotRecord,
    ExternalSource,
)

DEFERRED_STATUS = "deferred_missing_authorized_source"
BENCHMARK_DEFERRED = "deferred"
SOURCE_STATUSES = {"source_verified", "source_deferred", "source_rejected"}
POLICY_ARTIFACT_KEY = "configs/cycle40_external_source_policy.yaml"
REPORT_ARTIFACT_KEY = "reports/generated/cycle_40_source_readiness.json"
_RUNTIME_KEYS = {
    "policy_path",
    "report_path",
    "output_root",
    "hostname",
    "runtime_metadata",
    "report_file_sha256",
}
_HASH_KEYS = {"report_content_sha256", "manifest_file_sha256"}


def _canonicalize(value: Any) -> Any:
    """Normalize JSON-compatible values, including order-insensitive lists."""

    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        normalized = [_canonicalize(item) for item in value]
        return sorted(normalized, key=lambda item: _canonical_json(item))
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite numeric values are not canonicalizable")
        return value
    return value


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            _canonicalize(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_report_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Return report content excluding all runtime location and self-hash fields."""

    payload = {
        key: value
        for key, value in report.items()
        if key not in _RUNTIME_KEYS and key not in _HASH_KEYS
    }
    return _canonicalize(payload)


def report_content_sha256(report: dict[str, Any]) -> str:
    """Hash only portable, deterministic report content."""

    return _sha256_bytes(_canonical_json(canonical_report_payload(report)))


def _aware_utc(value: Any) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.tz_convert("UTC").to_pydatetime()


def load_external_policy(path: Path) -> dict[str, Any]:
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("external source policy must be a mapping")
    if policy.get("schema_version") != "cycle40-external-source-policy-v1":
        raise ValueError("unsupported external source policy schema")
    if policy.get("policy_version") != "cycle40-readiness-deferred-v1":
        raise ValueError("unsupported external source policy version")
    if policy.get("external_source_status") != DEFERRED_STATUS:
        raise ValueError("Cycle 40 policy must remain deferred without an authorized source")
    if policy.get("commercial_release") is not False:
        raise ValueError("external readiness requires commercial_release=false")
    cutoff = policy.get("cutoff_protocol", {})
    if (
        cutoff.get("timezone") != "UTC"
        or cutoff.get("require_captured_at_before_kickoff") is not True
    ):
        raise ValueError("external readiness requires explicit UTC pre-match cutoff")
    if cutoff.get("closing_odds_allowed") is not False:
        raise ValueError("closing odds are disabled in Cycle 40 readiness")
    protected = policy.get("protected_seasons", {})
    if "2526" not in protected.get("forbid_tuning_selection_calibration", []):
        raise ValueError("2526 must remain protected")
    if "2627" not in protected.get("future_holdout", []):
        raise ValueError("2627 must remain a future holdout")
    if not isinstance(policy.get("allowed_sources"), list):
        raise ValueError("allowed_sources must be a list")
    return policy


def _source_status(policy: dict[str, Any]) -> str:
    return "source_deferred" if not policy["allowed_sources"] else "source_rejected"


def deferred_readiness_report(
    policy: dict[str, Any],
    *,
    policy_path: Path | None = None,
    source_commit: str | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic no-source report; paths are runtime-only when supplied."""

    policy_bytes = _canonical_json(policy)
    report: dict[str, Any] = {
        "schema_version": "cycle40-external-source-readiness-v1",
        "external_source_status": DEFERRED_STATUS,
        "source_status": _source_status(policy),
        "source_count": 0,
        "allowed_source_count": len(policy["allowed_sources"]),
        "policy_artifact_key": POLICY_ARTIFACT_KEY,
        "report_artifact_key": REPORT_ARTIFACT_KEY,
        "policy_version": policy["policy_version"],
        "policy_sha256": _sha256_bytes(policy_bytes),
        "source_commit": source_commit,
        "cutoff_protocol": policy["cutoff_protocol"],
        "protected_seasons": policy["protected_seasons"],
        "raw_rows": 0,
        "valid_rows": 0,
        "matched_rows": 0,
        "unmatched_rows": 0,
        "ambiguous_rows": 0,
        "late_rows": 0,
        "missing_provenance": 0,
        "license_failures": 0,
        "duplicate_snapshots": 0,
        "schema_failures": 0,
        "coverage": [],
        "source_rejections_by_reason": {},
        "benchmark_status": BENCHMARK_DEFERRED,
        "commercial_release": False,
    }
    if policy_path is not None:
        report["runtime_metadata"] = {
            "policy_path": str(policy_path.resolve()),
        }
    if runtime_metadata:
        report.setdefault("runtime_metadata", {}).update(runtime_metadata)
    report["report_content_sha256"] = report_content_sha256(report)
    return report


def _record_identity(record: ExternalSnapshotRecord) -> tuple[str, ...]:
    return (
        record.source_name,
        record.request_or_snapshot_id,
        record.match_id or "",
        record.event_id or "",
        record.market or "",
        record.selection or "",
        record.captured_at_utc.isoformat(),
    )


def audit_snapshot_records(
    raw_records: list[dict[str, Any]],
    *,
    source: ExternalSource | None,
    policy: dict[str, Any],
    known_events: pd.DataFrame,
    cutoff_utc: datetime | None = None,
) -> dict[str, Any]:
    """Audit authorized records, isolating invalid rows instead of linking them randomly."""

    counters = Counter(
        raw_rows=len(raw_records),
        valid_rows=0,
        matched_rows=0,
        unmatched_rows=0,
        ambiguous_rows=0,
        late_rows=0,
        missing_provenance=0,
        license_failures=0,
        duplicate_snapshots=0,
        schema_failures=0,
    )
    reasons: Counter[str] = Counter()
    accepted: list[ExternalSnapshotRecord] = []
    seen: set[tuple[str, ...]] = set()
    cutoff = _aware_utc(cutoff_utc) if cutoff_utc is not None else None
    source_valid = source is not None
    if source is None:
        reasons["missing_authorized_source"] += len(raw_records)
        counters["missing_provenance"] += len(raw_records)
        source_valid = False
    elif not (source.license_name or source.license_url or source.license_policy_reference):
        counters["license_failures"] += 1
        reasons["missing_license_or_policy"] += 1
        source_valid = False
    event_frame = known_events.copy()
    if "match_id" not in event_frame:
        event_frame["match_id"] = pd.Series(index=event_frame.index, dtype="string")
    if "event_id" not in event_frame:
        event_frame["event_id"] = pd.Series(index=event_frame.index, dtype="string")
    event_frame["match_id"] = event_frame["match_id"].astype(str)
    event_frame["event_id"] = event_frame["event_id"].astype(str)
    for raw in raw_records:
        try:
            record = ExternalSnapshotRecord.model_validate(raw)
        except Exception as exc:
            message = str(exc)
            if "precede kickoff" in message:
                counters["late_rows"] += 1
                reasons["captured_at_at_or_after_kickoff"] += 1
            elif "license" in message or "timestamp" in message or "hash" in message:
                counters["missing_provenance"] += 1
                reasons["missing_provenance"] += 1
            else:
                counters["schema_failures"] += 1
                reasons["schema_failure"] += 1
            continue
        allowed = [
            item
            for item in policy["allowed_sources"]
            if item.get("source_name") == record.source_name
        ]
        if not allowed or record.source_version not in {
            item.get("source_version") for item in allowed
        }:
            counters["missing_provenance"] += 1
            reasons["source_not_allowlisted"] += 1
            continue
        if source is None or record.source_version != source.source_version:
            counters["missing_provenance"] += 1
            reasons["source_version_mismatch"] += 1
            continue
        if source is not None and record.input_sha256 != source.input_sha256:
            counters["missing_provenance"] += 1
            reasons["input_hash_mismatch"] += 1
            continue
        identity = _record_identity(record)
        if identity in seen:
            counters["duplicate_snapshots"] += 1
            reasons["duplicate_snapshot"] += 1
            continue
        seen.add(identity)
        counters["valid_rows"] += 1
        candidates = event_frame
        if record.match_id:
            candidates = candidates[candidates["match_id"] == record.match_id]
        elif record.event_id:
            candidates = candidates[candidates["event_id"] == record.event_id]
        if len(candidates) == 0:
            counters["unmatched_rows"] += 1
            reasons["unknown_match_or_event"] += 1
            continue
        if len(candidates) > 1:
            counters["ambiguous_rows"] += 1
            reasons["ambiguous_match"] += 1
            continue
        event_kickoff = _aware_utc(candidates.iloc[0]["kickoff_utc"])
        tolerance_seconds = (
            float(policy.get("matching", {}).get("kickoff_tolerance_minutes", 0)) * 60
        )
        if abs((record.kickoff_utc - event_kickoff).total_seconds()) > tolerance_seconds:
            counters["unmatched_rows"] += 1
            reasons["kickoff_mismatch_outside_tolerance"] += 1
            continue
        if record.captured_at_utc >= event_kickoff:
            counters["late_rows"] += 1
            reasons["captured_at_at_or_after_kickoff"] += 1
            continue
        if (
            cutoff is not None
            and record.available_at_utc is not None
            and record.available_at_utc >= cutoff
        ):
            counters["late_rows"] += 1
            reasons["available_at_at_or_after_cutoff"] += 1
            continue
        accepted.append(record)
        counters["matched_rows"] += 1
    source_status = (
        "source_verified" if source_valid and counters["matched_rows"] else "source_rejected"
    )
    return {
        "schema_version": "cycle40-external-source-readiness-v1",
        "external_source_status": "source_verified"
        if source_status == "source_verified"
        else "source_rejected",
        "source_status": source_status,
        **dict(counters),
        "accepted_snapshot_ids": sorted(record.request_or_snapshot_id for record in accepted),
        "source_rejections_by_reason": dict(sorted(reasons.items())),
        "benchmark_status": BENCHMARK_DEFERRED,
        "commercial_release": False,
    }


def write_readiness_report(
    report: dict[str, Any],
    destination: Path,
    *,
    runtime_metadata: dict[str, Any] | None = None,
) -> str:
    """Write a report and return its physical file hash, not its content hash."""

    if runtime_metadata:
        report.setdefault("runtime_metadata", {}).update(runtime_metadata)
    report["report_content_sha256"] = report_content_sha256(report)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return _sha256_bytes(payload.encode("utf-8"))


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _iter_strings(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _iter_strings(nested)]
    return [value] if isinstance(value, str) else []


def validate_readiness_report(report: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Validate portable report content without requiring its checkout path."""

    if not isinstance(report, dict):
        raise ValueError("readiness report must be a mapping")
    expected_policy_sha256 = _sha256_bytes(_canonical_json(policy))
    if report.get("policy_artifact_key") != POLICY_ARTIFACT_KEY:
        raise ValueError("policy_artifact_key mismatch")
    if report.get("report_artifact_key") != REPORT_ARTIFACT_KEY:
        raise ValueError("report_artifact_key mismatch")
    if report.get("policy_sha256") != expected_policy_sha256:
        raise ValueError("policy hash mismatch")
    expected_report_sha256 = report_content_sha256(report)
    if report.get("report_content_sha256") != expected_report_sha256:
        raise ValueError("report content hash mismatch")
    canonical = _canonical_json(canonical_report_payload(report)).decode("utf-8")
    if any(value.startswith("/") for value in _iter_strings(canonical_report_payload(report))):
        raise ValueError("absolute paths are not allowed in canonical report payload")
    if any(
        marker in canonical.lower()
        for marker in ("api_key", "access_token", "authorization", "password")
    ):
        raise ValueError("secrets are not allowed in canonical report payload")
    source_count = report.get("source_count")
    if source_count == 0:
        if report.get("external_source_status") != DEFERRED_STATUS:
            raise ValueError("zero sources must remain deferred")
        if report.get("source_status") != "source_deferred":
            raise ValueError("zero sources must have source_deferred status")
        if report.get("benchmark_status") != BENCHMARK_DEFERRED:
            raise ValueError("zero sources require deferred benchmark")
    if report.get("commercial_release") is not False:
        raise ValueError("readiness report requires commercial_release=false")
    return {
        "schema_version": report.get("schema_version"),
        "policy_sha256": expected_policy_sha256,
        "report_content_sha256": expected_report_sha256,
        "canonical_bytes": len(canonical.encode("utf-8")),
        "absolute_paths_in_canonical": False,
        "secrets_in_canonical": False,
        "commercial_release": False,
    }


def build_deferred_manifest(report: dict[str, Any]) -> dict[str, Any]:
    """Build a portable manifest whose physical file hash is computed externally."""

    return {
        "schema_version": "cycle40-external-source-manifest-v2",
        "manifest_type": "deferred_no_authorized_source",
        "external_source_status": DEFERRED_STATUS,
        "source_count": 0,
        "source_manifests": [],
        "policy_artifact_key": POLICY_ARTIFACT_KEY,
        "report_artifact_key": REPORT_ARTIFACT_KEY,
        "policy_sha256": report["policy_sha256"],
        "report_content_sha256": report["report_content_sha256"],
        "benchmark_status": BENCHMARK_DEFERRED,
        "commercial_release": False,
    }


def write_manifest(manifest: dict[str, Any], destination: Path) -> str:
    """Write exact manifest bytes and return the physical manifest file SHA-256."""

    payload = _canonical_json(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return _sha256_bytes(payload)


def validate_deferred_manifest(
    manifest: dict[str, Any],
    report: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Validate manifest linkage while keeping physical file hash separate."""

    validate_readiness_report(report, policy)
    expected = build_deferred_manifest(report)
    if manifest != expected:
        raise ValueError("deferred manifest content mismatch")
    return {
        "manifest_content_valid": True,
        "policy_sha256": report["policy_sha256"],
        "report_content_sha256": report["report_content_sha256"],
        "manifest_file_sha256_scope": "sha256 of exact manifest JSON bytes",
        "commercial_release": False,
    }
