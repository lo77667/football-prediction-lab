"""Fail-closed readiness checks for explicitly authorized external sources."""

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


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def deferred_readiness_report(policy: dict[str, Any], *, policy_path: Path) -> dict[str, Any]:
    """Build a deterministic no-source report without fabricating source or economic data."""

    policy_bytes = _canonical_json(policy)
    return {
        "schema_version": "cycle40-external-source-readiness-v1",
        "external_source_status": DEFERRED_STATUS,
        "source_status": _source_status(policy),
        "source_count": 0,
        "allowed_source_count": len(policy["allowed_sources"]),
        "policy_version": policy["policy_version"],
        "policy_path": str(policy_path.resolve()),
        "policy_sha256": _sha256_bytes(policy_bytes),
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
        "accepted_snapshot_ids": [record.request_or_snapshot_id for record in accepted],
        "source_rejections_by_reason": dict(sorted(reasons.items())),
        "benchmark_status": BENCHMARK_DEFERRED,
        "commercial_release": False,
    }


def write_readiness_report(report: dict[str, Any], destination: Path) -> str:
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return _sha256_bytes(payload.encode("utf-8"))
