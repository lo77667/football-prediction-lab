"""Local transport adapter; intentionally not an HTTP server."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.contracts import PredictionServiceRequest, ServiceError
from football_prediction_lab.service.errors import PredictionServiceError


def health(application: PredictionApplication, manifest_path: Any = None) -> dict[str, Any]:
    return application.health(manifest_path)


def version(application: PredictionApplication) -> dict[str, Any]:
    return application.version()


def post_shadow_prediction(
    application: PredictionApplication, payload: dict[str, Any]
) -> dict[str, Any]:
    """Validate and execute one local shadow request; no raw CSV input is accepted."""

    try:
        request = PredictionServiceRequest.model_validate(payload)
        response = application.predict(request)
    except ValidationError as exc:
        error = ServiceError(
            code="invalid_request",
            message="service request contract is invalid",
            field=str(exc.errors()[0].get("loc", ["request"])[0]),
            retryable=False,
        )
        return {"ok": False, "error": error.model_dump(mode="json")}
    except PredictionServiceError as exc:
        error = ServiceError(**exc.as_dict())
        return {"ok": False, "error": error.model_dump(mode="json")}
    except Exception:
        error = ServiceError(
            code="blocked_provenance",
            message="request could not be verified",
            retryable=False,
        )
        return {"ok": False, "error": error.model_dump(mode="json")}
    return {"ok": True, "response": response.model_dump(mode="json")}
