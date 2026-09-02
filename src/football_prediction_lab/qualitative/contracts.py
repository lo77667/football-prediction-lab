"""Auditable contracts for time-aware qualitative football information."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

QualitativeCategory = Literal[
    "injury",
    "suspension",
    "lineup",
    "news",
    "referee_context",
    "match_importance",
    "weather",
    "other",
]
RightsStatus = Literal["public_domain", "research_permitted", "permission_recorded"]


class SourceProvenance(BaseModel):
    """Rights and retrieval metadata required before a qualitative event is trainable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: HttpUrl | None = None
    source_id: str | None = Field(default=None, min_length=1)
    accessed_at_utc: AwareDatetime
    rights_status: RightsStatus
    rights_reviewed_at_utc: AwareDatetime
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_source_identity(self) -> SourceProvenance:
        if self.source_url is None and self.source_id is None:
            raise ValueError("at least one provenance source_url or source_id is required")
        return self


class QualitativeEvent(BaseModel):
    """A source-backed qualitative fact that can be audited at a cutoff time."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    available_at_utc: AwareDatetime
    observed_at_utc: AwareDatetime | None = None
    source_url: HttpUrl | None = None
    source_id: str | None = Field(default=None, min_length=1)
    provenance: SourceProvenance | None = None
    category: QualitativeCategory
    normalized_value: dict[str, Any] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> QualitativeEvent:
        if self.source_url is None and self.source_id is None:
            raise ValueError("at least one of source_url or source_id is required")
        if self.observed_at_utc is not None and self.observed_at_utc > self.available_at_utc:
            raise ValueError("observed_at_utc cannot be later than available_at_utc")
        if (
            self.provenance is not None
            and self.source_id is not None
            and self.provenance.source_id is not None
            and self.source_id != self.provenance.source_id
        ):
            raise ValueError("event source_id must match provenance source_id")
        if (
            self.provenance is not None
            and self.source_url is not None
            and self.provenance.source_url is not None
            and self.source_url != self.provenance.source_url
        ):
            raise ValueError("event source_url must match provenance source_url")
        return self

    def is_available_at(self, cutoff_utc: datetime) -> bool:
        """Return whether this event was available by a timezone-aware cutoff."""

        if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
            raise ValueError("cutoff_utc must be timezone-aware")
        return self.available_at_utc <= cutoff_utc

    def is_training_eligible(self) -> bool:
        """Return whether rights and source retrieval metadata are complete."""

        return self.provenance is not None


class QualitativeFeatureSet(BaseModel):
    """A match-scoped collection of qualitative events at a declared cutoff."""

    model_config = ConfigDict(extra="forbid")

    match_id: str = Field(min_length=1)
    cutoff_utc: AwareDatetime
    events: list[QualitativeEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_match_scope(self) -> QualitativeFeatureSet:
        mismatched = [event.event_id for event in self.events if event.match_id != self.match_id]
        if mismatched:
            raise ValueError(f"events belong to another match: {mismatched}")
        return self

    def available_events(self) -> list[QualitativeEvent]:
        """Return only source-backed events available before the declared cutoff."""

        return sorted(
            (event for event in self.events if event.is_available_at(self.cutoff_utc)),
            key=lambda event: (event.available_at_utc, event.event_id),
        )


def filter_events_before_cutoff(
    events: list[QualitativeEvent], cutoff_utc: datetime
) -> list[QualitativeEvent]:
    """Apply the point-in-time availability filter."""

    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    return sorted(
        (event for event in events if event.is_available_at(cutoff_utc)),
        key=lambda event: (event.available_at_utc, event.event_id),
    )


def filter_events_for_training(
    events: list[QualitativeEvent], cutoff_utc: datetime
) -> list[QualitativeEvent]:
    """Return only cutoff-safe events with recorded provenance and rights metadata."""

    return [
        event
        for event in filter_events_before_cutoff(events, cutoff_utc)
        if event.is_training_eligible()
    ]
