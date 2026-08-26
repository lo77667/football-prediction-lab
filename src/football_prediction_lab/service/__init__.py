"""Local Prediction Service Core for Cycle 41."""

from football_prediction_lab.service.contracts import (
    PredictionServiceRequest,
    PredictionServiceResponse,
    ServiceError,
    ServiceOperationalMetrics,
)
from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    SERVICE_VERSION,
    version_payload,
)

__all__ = [
    "FEATURE_VERSION",
    "MODEL_VERSION",
    "POLICY_VERSION",
    "PredictionServiceRequest",
    "PredictionServiceResponse",
    "SERVICE_VERSION",
    "ServiceError",
    "ServiceOperationalMetrics",
    "version_payload",
]
