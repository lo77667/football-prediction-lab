"""Strict request, response, and service-error contracts for Cycle 41."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from football_prediction_lab.shadow.contracts import ShadowPrediction

_HEX64_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^(?:[0-9a-f]{40}|unknown)$"
_SECRET_MARKERS = ("api_key", "access_token", "authorization", "password", "secret")
_FORBIDDEN_PAYLOAD_KEYS = {
    "target",
    "result",
    "odds",
    "roi",
    "ev",
    "stake",
    "btts",
    "home_goals",
    "away_goals",
    "fthg",
    "ftag",
    "ftr",
}


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC")
    return value.astimezone(UTC)


class PredictionServiceRequest(BaseModel):
    """Internal-only request; it carries references, never raw features."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    manifest_fingerprint: str = Field(pattern=_HEX64_PATTERN)
    as_of_utc: AwareDatetime
    market: Literal["btts", "cards"]
    policy_version: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    feature_version: str = Field(min_length=1, max_length=128)
    expected_source_commit: str = Field(pattern=_COMMIT_PATTERN)
    mode: Literal["shadow"] = "shadow"

    @field_validator("as_of_utc")
    @classmethod
    def validate_as_of_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @field_validator(
        "request_id",
        "policy_version",
        "model_version",
        "feature_version",
        "expected_source_commit",
    )
    @classmethod
    def reject_sensitive_text(cls, value: str) -> str:
        lowered = value.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS) or value.startswith("/"):
            raise ValueError("request contains disallowed sensitive or path-like text")
        return value


class ServiceOperationalMetrics(BaseModel):
    """Stable counters only; paths, timestamps, and data contents are excluded."""

    model_config = ConfigDict(extra="forbid")

    predictions_issued: int = Field(ge=0)
    skipped_items: int = Field(ge=0)
    ledger_records: int = Field(ge=0)
    idempotent_replay: bool


class PredictionServiceResponse(BaseModel):
    """Prelabel response with deterministic content hash and no financial fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=128)
    service_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    manifest_fingerprint: str = Field(pattern=_HEX64_PATTERN)
    as_of_utc: AwareDatetime
    predictions: list[ShadowPrediction]
    skipped: list[dict[str, Any]]
    operational_metrics: ServiceOperationalMetrics
    response_content_sha256: str = Field(pattern=_HEX64_PATTERN)
    commercial_release: Literal[False] = False

    @field_validator("as_of_utc")
    @classmethod
    def validate_response_as_of_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def reject_forbidden_content(self) -> PredictionServiceResponse:
        def scan(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if str(key).lower() in _FORBIDDEN_PAYLOAD_KEYS:
                        raise ValueError("response contains forbidden target or financial field")
                    scan(child)
            elif isinstance(value, list):
                for child in value:
                    scan(child)
            elif isinstance(value, str):
                lowered = value.lower()
                if any(marker in lowered for marker in _SECRET_MARKERS):
                    raise ValueError("response contains sensitive text")

        scan(self.skipped)
        if self.commercial_release is not False:
            raise ValueError("service response requires commercial_release=false")
        return self


class ServiceError(BaseModel):
    """Safe error envelope; messages never include raw inputs or secret material."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_:-]+$")
    message: str = Field(min_length=1, max_length=256)
    field: str | None = Field(default=None, max_length=96)
    retryable: bool = False
    provenance_details: dict[str, str | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_error_content(self) -> ServiceError:
        values = [
            self.message,
            self.field or "",
            *[str(value) for value in self.provenance_details.values()],
        ]
        joined = " ".join(values).lower()
        if any(marker in joined for marker in _SECRET_MARKERS) or any(
            value.startswith("/") for value in values
        ):
            raise ValueError("service error contains sensitive or path-like text")
        return self
