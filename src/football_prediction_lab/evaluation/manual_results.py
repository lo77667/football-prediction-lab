"""Append-only manual result tracking for internal shadow evaluation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_FORBIDDEN_TERMS = {
    "odds",
    "roi",
    "ev",
    "stake",
    "api_key",
    "authorization",
    "token",
}


class ManualResultRecord(BaseModel):
    """A post-match result attached to one internal shadow prediction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction_id: str = Field(min_length=1, max_length=128)
    match_id: str = Field(min_length=1, max_length=128)
    market: str = Field(min_length=1, max_length=64)
    kickoff_utc: datetime
    outcome_label: str = Field(min_length=1, max_length=64)
    recorded_at_utc: datetime
    result_source: str = Field(min_length=1, max_length=128)
    source_snapshot_id: str = Field(min_length=1, max_length=128)

    @field_validator(
        "prediction_id",
        "match_id",
        "market",
        "outcome_label",
        "result_source",
        "source_snapshot_id",
    )
    @classmethod
    def reject_sensitive_text(cls, value: str) -> str:
        lowered = value.lower()
        if any(term in lowered for term in _FORBIDDEN_TERMS):
            raise ValueError("sensitive or financial terms are not allowed")
        if any(char in value for char in ("\r", "\n", "\x00")):
            raise ValueError("control characters are not allowed")
        return value

    @model_validator(mode="after")
    def validate_timing(self) -> ManualResultRecord:
        for name in ("kickoff_utc", "recorded_at_utc"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            if value.utcoffset().total_seconds() != 0:
                raise ValueError(f"{name} must be explicit UTC")
        if self.recorded_at_utc <= self.kickoff_utc:
            raise ValueError("result cannot be recorded before or at kickoff")
        return self


class ManualResultLedger:
    """Idempotent, append-only JSONL ledger with no network transport."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def record_id(record: ManualResultRecord) -> str:
        payload = record.model_dump(mode="json")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def append(self, record: ManualResultRecord) -> str:
        identifier = self.record_id(record)
        if identifier in self.ids():
            return identifier
        event = {
            "event": "manual_result_recorded",
            "record_id": identifier,
            "record": record.model_dump(mode="json"),
            "commercial_release": False,
        }
        line = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return identifier

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def ids(self) -> set[str]:
        return {str(event["record_id"]) for event in self.events() if "record_id" in event}
