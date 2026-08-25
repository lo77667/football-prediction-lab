"""Boundary validation and idempotency helpers for warehouse ingestion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionReceipt(BaseModel):
    """Serializable receipt for replay-safe ingestion."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    received_at_utc: datetime
    status: str = Field(pattern=r"^(received|processed|quarantined|failed)$")
    retry_count: int = Field(ge=0, default=0)
    error_class: str | None = None


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a JSON mapping deterministically for idempotency and provenance."""

    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_receipt(
    *,
    source_system: str,
    source_record_id: str,
    payload: Mapping[str, Any],
    status: str = "received",
    retry_count: int = 0,
    error_class: str | None = None,
) -> IngestionReceipt:
    """Create a receipt whose ID is stable for the source and content hash."""

    source_sha256 = canonical_sha256(payload)
    receipt_id = f"{source_system}:{source_record_id}:{source_sha256[:16]}"
    return IngestionReceipt(
        receipt_id=receipt_id,
        source_system=source_system,
        source_record_id=source_record_id,
        source_sha256=source_sha256,
        received_at_utc=datetime.now(UTC),
        status=status,
        retry_count=retry_count,
        error_class=error_class,
    )


@dataclass(frozen=True)
class QuarantineRecord:
    """A failed record retained without being written to analytical tables."""

    receipt: IngestionReceipt
    reason: str
    payload_sha256: str


def quarantine(
    *,
    source_system: str,
    source_record_id: str,
    payload: Mapping[str, Any],
    reason: str,
) -> QuarantineRecord:
    """Create a safe quarantine record with no raw payload copy."""

    receipt = make_receipt(
        source_system=source_system,
        source_record_id=source_record_id,
        payload=payload,
        status="quarantined",
        error_class=reason,
    )
    return QuarantineRecord(receipt=receipt, reason=reason, payload_sha256=receipt.source_sha256)
