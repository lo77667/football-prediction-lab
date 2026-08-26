"""Strict contracts for authorized external-source readiness and pre-match snapshots."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SECRET_MARKER = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|bearer|password|secret)\s*[:=]",
    re.IGNORECASE,
)


class ExternalSource(BaseModel):
    """Non-secret provenance metadata for an authorized external source."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    endpoint_or_dataset_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    license_name: str | None = None
    license_url: HttpUrl | None = None
    license_policy_reference: str | None = None
    allowed_reuse: bool
    retrieved_at_utc: AwareDatetime
    available_at_utc: AwareDatetime | None = None
    request_or_snapshot_id: str = Field(min_length=1)
    input_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_version: str = Field(min_length=1)
    retention_policy: str = Field(min_length=1)
    contact_owner: str | None = None
    commercial_release: Literal[False] = False

    @model_validator(mode="after")
    def validate_provenance(self) -> ExternalSource:
        if not (self.license_name or self.license_url or self.license_policy_reference):
            raise ValueError(
                "source requires license_name, license_url, or license_policy_reference"
            )
        if self.available_at_utc is not None and self.available_at_utc > self.retrieved_at_utc:
            raise ValueError("available_at_utc must not follow retrieved_at_utc")
        if _SECRET_MARKER.search(self.endpoint_or_dataset_id):
            raise ValueError("secrets are not allowed in endpoint_or_dataset_id")
        if self.contact_owner and _SECRET_MARKER.search(self.contact_owner):
            raise ValueError("secrets are not allowed in contact_owner")
        return self


class ExternalSnapshotRecord(BaseModel):
    """One source observation that can be checked against a deterministic event."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    request_or_snapshot_id: str = Field(min_length=1)
    snapshot_version: str = Field(min_length=1)
    input_sha256: str = Field(pattern=SHA256_PATTERN)
    match_id: str | None = None
    event_id: str | None = None
    kickoff_utc: AwareDatetime
    captured_at_utc: AwareDatetime
    available_at_utc: AwareDatetime | None = None
    market: str | None = None
    market_definition: str | None = None
    selection: str | None = None
    decimal_odds: float | None = Field(default=None, gt=1.0)
    odds_type: Literal["opening", "pre_match", "closing"] | None = None

    @model_validator(mode="after")
    def validate_record(self) -> ExternalSnapshotRecord:
        if not (self.match_id or self.event_id):
            raise ValueError("snapshot requires match_id or event_id")
        if self.captured_at_utc >= self.kickoff_utc:
            raise ValueError("captured_at_utc must precede kickoff_utc for pre-match data")
        if self.available_at_utc is not None and self.available_at_utc >= self.kickoff_utc:
            raise ValueError("available_at_utc must precede kickoff_utc for pre-match data")
        if self.available_at_utc is not None and self.available_at_utc > self.captured_at_utc:
            raise ValueError("available_at_utc must not follow captured_at_utc")
        odds_fields = (
            self.decimal_odds,
            self.market,
            self.market_definition,
            self.selection,
            self.odds_type,
        )
        if any(value is not None for value in odds_fields) and not all(
            value is not None for value in odds_fields
        ):
            raise ValueError(
                "odds snapshot requires market, definition, selection, odds_type, and decimal_odds"
            )
        return self
