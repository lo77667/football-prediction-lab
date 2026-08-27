"""Fixture-only odds adapter; no network transport is provided here."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from football_prediction_lab.ingestion.external_contracts import (
    ExternalSnapshotRecord,
    ExternalSource,
)

_ALLOWED_FIELDS = {
    "request_or_snapshot_id",
    "snapshot_version",
    "match_id",
    "event_id",
    "kickoff_utc",
    "captured_at_utc",
    "available_at_utc",
    "market",
    "market_definition",
    "selection",
    "decimal_odds",
    "odds_type",
}


@dataclass(frozen=True)
class OddsAdapterResult:
    records: tuple[ExternalSnapshotRecord, ...]
    raw_rows: int
    accepted_rows: int
    rejected_by_reason: dict[str, int]
    input_sha256: str


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be explicit UTC")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def adapt_odds_payload(
    payload: list[dict[str, Any]],
    *,
    source: ExternalSource,
    event_kickoffs_utc: dict[str, datetime],
) -> OddsAdapterResult:
    """Validate local fixture payload against trusted event kickoffs.

    This function never opens a socket and never computes EV, ROI, or stake sizing.
    """

    encoded = _canonical(payload)
    input_sha256 = hashlib.sha256(encoded).hexdigest()
    if not source.allowed_reuse:
        return OddsAdapterResult(
            records=(),
            raw_rows=len(payload),
            accepted_rows=0,
            rejected_by_reason={"source_not_reusable": len(payload)},
            input_sha256=input_sha256,
        )

    rejected: Counter[str] = Counter()
    records: list[ExternalSnapshotRecord] = []
    for row in payload:
        try:
            unknown = set(row) - _ALLOWED_FIELDS
            if unknown:
                raise ValueError("unknown odds fields")
            match_key = str(row.get("match_id") or row.get("event_id") or "")
            trusted_kickoff = event_kickoffs_utc.get(match_key)
            if trusted_kickoff is None:
                raise ValueError("unknown event")
            record_payload = {
                **row,
                "source_name": source.source_name,
                "source_version": source.source_version,
                "request_or_snapshot_id": row.get("request_or_snapshot_id", ""),
                "snapshot_version": row.get("snapshot_version", "v1"),
                "kickoff_utc": _iso(trusted_kickoff),
                "input_sha256": input_sha256,
            }
            record = ExternalSnapshotRecord.model_validate(record_payload)
            records.append(record)
        except Exception as error:
            rejected[f"invalid_row:{type(error).__name__}"] += 1
            continue
    return OddsAdapterResult(
        records=tuple(records),
        raw_rows=len(payload),
        accepted_rows=len(records),
        rejected_by_reason=dict(sorted(rejected.items())),
        input_sha256=input_sha256,
    )
