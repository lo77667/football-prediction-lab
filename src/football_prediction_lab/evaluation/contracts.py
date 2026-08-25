"""Auditable contracts for pre-match prediction records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class OddsProvenance(BaseModel):
    """Timestamped odds metadata; odds are optional and never inferred."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decimal_odds: float = Field(gt=1.0)
    odds_timestamp: AwareDatetime
    source: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    provenance_id: str = Field(min_length=1)


class PredictionRecord(BaseModel):
    """One pre-match prediction with point-in-time and provenance metadata."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prediction_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    market_definition: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    issued_at: AwareDatetime
    kickoff_utc: AwareDatetime
    probability: float = Field(ge=0.0, le=1.0)
    threshold: float | None = Field(default=None, gt=0.0, lt=1.0)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    training_cutoff: AwareDatetime
    input_provenance: list[str] = Field(min_length=1)
    odds: OddsProvenance | None = None

    @model_validator(mode="after")
    def validate_point_in_time(self) -> PredictionRecord:
        if self.market_definition.lower() in {"unknown", "n/a", "unspecified"}:
            raise ValueError("market_definition must be explicit")
        if any(not source.strip() for source in self.input_provenance):
            raise ValueError("input_provenance entries must be non-empty")
        if self.issued_at >= self.kickoff_utc:
            raise ValueError("issued_at must precede kickoff_utc")
        if self.training_cutoff >= self.issued_at:
            raise ValueError("training_cutoff must precede issued_at")
        if self.odds is not None and self.odds.odds_timestamp >= self.kickoff_utc:
            raise ValueError("odds_timestamp must precede kickoff_utc")
        return self

    def as_audit_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible record for a validation ledger."""

        return self.model_dump(mode="json")


def validate_prediction_ledger(records: list[PredictionRecord]) -> None:
    """Reject duplicate IDs or mixed market definitions for one market."""

    ids = [record.prediction_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("prediction_id values must be unique")
    definitions: dict[str, set[str]] = {}
    for record in records:
        definitions.setdefault(record.market, set()).add(record.market_definition)
    if any(len(values) > 1 for values in definitions.values()):
        raise ValueError("market definitions must not be mixed")


def ensure_aware(value: datetime) -> None:
    """Reject naive datetimes at validation boundaries."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
