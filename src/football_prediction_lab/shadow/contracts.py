from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ShadowPrediction(BaseModel):
    """One pre-match shadow prediction with immutable provenance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prediction_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    market_definition: str = Field(min_length=1)
    kickoff_utc: AwareDatetime
    issued_at_utc: AwareDatetime
    as_of_utc: AwareDatetime
    training_cutoff: AwareDatetime
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    feature_provenance_hash: str = Field(min_length=1)
    source_manifest_fingerprint: str = Field(min_length=1)
    selected_policy_variant: str = Field(min_length=1)
    status: Literal["issued"] = "issued"

    @model_validator(mode="after")
    def validate_point_in_time(self) -> ShadowPrediction:
        if self.issued_at_utc > self.as_of_utc:
            raise ValueError("issued_at_utc must be at or before as_of_utc")
        if self.as_of_utc >= self.kickoff_utc:
            raise ValueError("as_of_utc must precede kickoff_utc")
        if self.training_cutoff >= self.as_of_utc:
            raise ValueError("training_cutoff must precede as_of_utc")
        if self.market_definition.lower() in {"unknown", "n/a", "unspecified"}:
            raise ValueError("market_definition must be explicit")
        return self


class ShadowRun(BaseModel):
    """Operational metadata for one deterministic shadow issuance run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    run_id: str = Field(min_length=1)
    as_of_utc: AwareDatetime
    started_at_utc: AwareDatetime
    completed_at_utc: AwareDatetime
    source_manifest_fingerprint: str = Field(min_length=1)
    input_sha256: str = Field(min_length=1)
    feature_input_sha256: str = Field(min_length=1)
    code_commit: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    training_cutoff: AwareDatetime
    rows_seen: int = Field(ge=0)
    predictions_issued: int = Field(ge=0)
    rows_skipped: int = Field(ge=0)
    rejection_counts: dict[str, int]
    status: Literal["completed", "failed"]
    output_sha256: str = Field(min_length=1)
    ledger_sha256: str = Field(min_length=1)
    commercial_release: Literal[False] = False

    @model_validator(mode="after")
    def validate_run_times(self) -> ShadowRun:
        if self.started_at_utc > self.completed_at_utc:
            raise ValueError("started_at_utc must not follow completed_at_utc")
        if self.training_cutoff >= self.as_of_utc:
            raise ValueError("training_cutoff must precede as_of_utc")
        if any(value < 0 for value in self.rejection_counts.values()):
            raise ValueError("rejection counters must be non-negative")
        return self

    def as_audit_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
