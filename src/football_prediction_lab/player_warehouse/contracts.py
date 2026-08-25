"""Typed contracts for the youth-player hybrid warehouse."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

QualitativeTrait = Literal[
    "confidence",
    "communication",
    "coachability",
    "attention",
    "recovery_mindset",
    "competitive_response",
    "readiness",
    "other",
]
ReviewStatus = Literal[
    "not_reviewed",
    "coach_reviewed",
    "sports_science_reviewed",
    "safeguarding_restricted",
    "rejected",
]


class QualitativeMarkerEvent(BaseModel):
    """A source-backed, non-clinical marker available at a declared time."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    trait: QualitativeTrait
    value: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at_utc: AwareDatetime
    available_at_utc: AwareDatetime
    evidence_ref: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    review_status: ReviewStatus = "not_reviewed"
    context: str | None = None

    @model_validator(mode="after")
    def validate_time_order(self) -> QualitativeMarkerEvent:
        if self.available_at_utc < self.observed_at_utc:
            raise ValueError("available_at_utc cannot be earlier than observed_at_utc")
        return self

    def is_eligible_at(self, cutoff_utc: datetime) -> bool:
        """Return whether this reviewed event is safe to use at a cutoff."""

        if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
            raise ValueError("cutoff_utc must be timezone-aware")
        return self.available_at_utc <= cutoff_utc and self.review_status != "rejected"


class PlayerOutcome(BaseModel):
    """Future outcome used as a label, kept separate from predictor features."""

    model_config = ConfigDict(extra="forbid")

    player_id: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    target_value: float
    window_start_utc: AwareDatetime
    window_end_utc: AwareDatetime
    available_at_utc: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> PlayerOutcome:
        if self.window_end_utc <= self.window_start_utc:
            raise ValueError("outcome window_end_utc must be after window_start_utc")
        if self.available_at_utc < self.window_end_utc:
            raise ValueError("outcome available_at_utc cannot precede the outcome window")
        return self
