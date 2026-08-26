"""Safe application errors for the local Prediction Service Core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PredictionServiceError(Exception):
    """Internal error with a stable public code and redacted context."""

    code: str
    message: str
    field: str | None = None
    retryable: bool = False
    provenance_details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)
        self.provenance_details = dict(self.provenance_details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "retryable": self.retryable,
            "provenance_details": self.provenance_details,
        }


class ProvenanceBlocked(PredictionServiceError):
    def __init__(
        self, message: str = "verified manifest provenance is required", **details: Any
    ) -> None:
        super().__init__("blocked_provenance", message, retryable=False, provenance_details=details)


class InvalidServiceRequest(PredictionServiceError):
    def __init__(
        self, message: str = "service request is invalid", field: str | None = None
    ) -> None:
        super().__init__("invalid_request", message, field=field, retryable=False)


class ManifestPathRejected(PredictionServiceError):
    def __init__(self) -> None:
        super().__init__(
            "manifest_path_rejected",
            "manifest path is outside the allowed root",
            field="manifest_path",
        )


class ContractMismatch(PredictionServiceError):
    def __init__(self, field: str) -> None:
        super().__init__(
            "contract_mismatch", "request contract does not match verified provenance", field=field
        )
