"""Fail-closed contract for pre-match AI-assisted analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "ai-analysis-v1"
_FORBIDDEN_KEYS = {
    "authorization",
    "bot_token",
    "ev",
    "odds",
    "password",
    "raw_data",
    "result",
    "roi",
    "secret",
    "stake",
    "target",
    "token",
}


class AIAnalysisError(ValueError):
    """Raised when AI output cannot be verified against the pre-match contract."""


class AnalysisEvidence(BaseModel):
    """A source reference supplied to the model; the model cannot create one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=128)
    source_name: str = Field(min_length=1, max_length=128)
    source_url: str = Field(min_length=1, max_length=2048)
    captured_at_utc: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("captured_at_utc")
    @classmethod
    def require_explicit_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("captured_at_utc must be explicit UTC")
        return value.astimezone(UTC)


class AnalysisRequest(BaseModel):
    """Only pre-match context is eligible for AI analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    match_id: str = Field(min_length=1, max_length=128)
    kickoff_utc: datetime
    as_of_utc: datetime
    evidence: tuple[AnalysisEvidence, ...] = Field(default_factory=tuple)

    @field_validator("kickoff_utc", "as_of_utc")
    @classmethod
    def require_explicit_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("timestamps must be explicit UTC")
        return value.astimezone(UTC)

    def validate_cutoff(self) -> None:
        if self.as_of_utc >= self.kickoff_utc:
            raise AIAnalysisError("analysis cutoff must precede kickoff")


class VerifiedSignal(BaseModel):
    """A qualitative signal that must point to supplied evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=512)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class AIAnalysis(BaseModel):
    """Strict, non-predictive analysis output; no probability or label is accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION]
    match_id: str = Field(min_length=1, max_length=128)
    as_of_utc: datetime
    status: Literal["supported", "insufficient_evidence"]
    signals: tuple[VerifiedSignal, ...] = Field(default_factory=tuple, max_length=16)
    missing_information: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    unsupported_claims: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)

    @field_validator("as_of_utc")
    @classmethod
    def require_explicit_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("as_of_utc must be explicit UTC")
        return value.astimezone(UTC)


def _key_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {
            name for child in value.values() for name in _key_names(child)
        }
    if isinstance(value, list):
        return {name for child in value for name in _key_names(child)}
    return set()


def validate_ai_output(raw: Any, request: AnalysisRequest) -> AIAnalysis:
    """Validate structure, evidence references, and temporal safety; reject on any doubt."""

    request.validate_cutoff()
    if not isinstance(raw, dict):
        raise AIAnalysisError("AI output must be a JSON object")
    forbidden = _FORBIDDEN_KEYS.intersection(_key_names(raw))
    if forbidden:
        raise AIAnalysisError(f"forbidden output fields: {sorted(forbidden)}")
    try:
        output = AIAnalysis.model_validate(raw)
    except ValueError as error:
        raise AIAnalysisError("AI output failed schema validation") from error
    if output.match_id != request.match_id:
        raise AIAnalysisError("AI output match_id does not match request")
    if output.as_of_utc != request.as_of_utc:
        raise AIAnalysisError("AI output as_of_utc does not match request")
    if output.unsupported_claims:
        raise AIAnalysisError("unsupported claims require quarantine")
    allowed_evidence = {item.evidence_id for item in request.evidence}
    for signal in output.signals:
        if not set(signal.evidence_ids).issubset(allowed_evidence):
            raise AIAnalysisError("signal references evidence not present in request")
    if output.status == "supported" and not output.signals:
        raise AIAnalysisError("supported output must contain at least one evidence-backed signal")
    return output
