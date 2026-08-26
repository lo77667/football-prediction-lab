"""Strict contracts for auditable local ingestion runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class SourceRecord(BaseModel):
    """Metadata for the exact source file consumed by an ingestion run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    retrieved_at_utc: datetime
    input_path: str = Field(min_length=1)
    input_sha256: SHA256
    license_or_usage_policy: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    row_count: int = Field(ge=0)

    _normalize_retrieved_at = field_validator("retrieved_at_utc")(_aware_utc)


class MatchRecord(BaseModel):
    """A pre-match identity record; targets and post-match fields are excluded."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    match_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    competition: str = Field(min_length=1)
    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    kickoff_utc: datetime
    source_provenance_id: str = Field(min_length=1)
    ingestion_run_id: str = Field(min_length=1)
    record_version: int = Field(ge=1)

    _normalize_kickoff = field_validator("kickoff_utc")(_aware_utc)


class IngestionRun(BaseModel):
    """Auditable lifecycle and counts for one deterministic ingestion attempt."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    run_id: str = Field(min_length=1)
    started_at_utc: datetime
    completed_at_utc: datetime
    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    code_commit: str = Field(min_length=1)
    input_hash: SHA256
    output_hash: SHA256
    rows_read: int = Field(ge=0)
    rows_accepted: int = Field(ge=0)
    rows_quarantined: int = Field(ge=0)
    status: str = Field(pattern=r"^(completed|failed|quarantined)$")
    error_summary: list[str] = Field(default_factory=list)

    _normalize_started = field_validator("started_at_utc")(_aware_utc)
    _normalize_completed = field_validator("completed_at_utc")(_aware_utc)

    @field_validator("completed_at_utc")
    @classmethod
    def completed_after_started(cls, value: datetime, info: object) -> datetime:
        started = getattr(info, "data", {}).get("started_at_utc")
        if started is not None and value < started:
            raise ValueError("completed_at_utc must not precede started_at_utc")
        return value

    @field_validator("rows_accepted", "rows_quarantined")
    @classmethod
    def counts_nonnegative_and_bounded(cls, value: int, info: object) -> int:
        rows_read = getattr(info, "data", {}).get("rows_read")
        if rows_read is not None and value > rows_read:
            raise ValueError("accepted/quarantined rows cannot exceed rows_read")
        return value

    @field_validator("output_hash")
    @classmethod
    def output_hash_required_for_completed(cls, value: str, info: object) -> str:
        status = getattr(info, "data", {}).get("status")
        if status in {"completed", "quarantined"} and not value:
            raise ValueError("completed ingestion requires output_hash")
        return value
