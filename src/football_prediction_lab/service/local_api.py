"""Loopback-only HTTP adapter for the Cycle 42 local prediction service."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.contracts import (
    PredictionServiceRequest,
    PredictionServiceResponse,
    ServiceError,
)
from football_prediction_lab.service.transport import post_shadow_prediction

DEFAULT_MAX_BODY_BYTES = 64 * 1024

_ERROR_STATUS: dict[str, int] = {
    "invalid_request": HTTPStatus.BAD_REQUEST,
    "manifest_path_rejected": HTTPStatus.BAD_REQUEST,
    "contract_mismatch": HTTPStatus.CONFLICT,
    "blocked_provenance": HTTPStatus.SERVICE_UNAVAILABLE,
    "payload_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    "not_found": HTTPStatus.NOT_FOUND,
    "method_not_allowed": HTTPStatus.METHOD_NOT_ALLOWED,
    "unsupported_media_type": HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
}


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def openapi_schema() -> dict[str, Any]:
    """Return a deterministic, local-only OpenAPI snapshot payload."""

    request_schema = PredictionServiceRequest.model_json_schema()
    response_schema = PredictionServiceResponse.model_json_schema()
    error_schema = ServiceError.model_json_schema()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Football Prediction Lab Local Shadow API",
            "version": "cycle42-local-api-v1",
            "description": "Loopback-only adapter over the prelabel Prediction Service Core.",
        },
        "servers": [{"url": "http://127.0.0.1"}],
        "paths": {
            "/health": {
                "get": {
                    "operationId": "health",
                    "responses": {"200": {"description": "Process health state"}},
                }
            },
            "/ready": {
                "get": {
                    "operationId": "ready",
                    "responses": {"200": {"description": "Verified artifact readiness state"}},
                }
            },
            "/version": {
                "get": {
                    "operationId": "version",
                    "responses": {"200": {"description": "Service version and provenance"}},
                }
            },
            "/v1/shadow/predictions": {
                "post": {
                    "operationId": "postShadowPrediction",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PredictionServiceRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Verified prelabel shadow response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ServiceSuccessEnvelope"
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request or rejected manifest path",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ServiceErrorEnvelope"}
                                }
                            },
                        },
                        "409": {"description": "Provenance or version mismatch"},
                        "413": {"description": "Payload exceeds local limit"},
                        "503": {"description": "Provenance could not be verified"},
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "operationId": "openapi",
                    "responses": {"200": {"description": "This deterministic OpenAPI snapshot"}},
                }
            },
        },
        "components": {
            "schemas": {
                "PredictionServiceRequest": request_schema,
                "PredictionServiceResponse": response_schema,
                "ServiceError": error_schema,
                "ServiceSuccessEnvelope": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ok", "response"],
                    "properties": {
                        "ok": {"const": True},
                        "response": {"$ref": "#/components/schemas/PredictionServiceResponse"},
                    },
                },
                "ServiceErrorEnvelope": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ok", "error"],
                    "properties": {
                        "ok": {"const": False},
                        "error": {"$ref": "#/components/schemas/ServiceError"},
                    },
                },
            }
        },
    }


class LocalServiceAPI:
    """Pure local request dispatcher; no external network or raw-data input."""

    def __init__(
        self,
        application: PredictionApplication,
        *,
        readiness_run_dir: Path | None = None,
        audit_path: Path | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.application = application
        self.readiness_run_dir = readiness_run_dir
        self.audit_path = audit_path
        self.max_body_bytes = max_body_bytes
        self._audit_lock = threading.Lock()

    def _audit(self, *, method: str, path: str, status: int, error_code: str | None = None) -> None:
        event: dict[str, Any] = {
            "event": "local_api_request",
            "method": method,
            "path": path,
            "status": status,
            "commercial_release": False,
        }
        if error_code is not None:
            event["error_code"] = error_code
        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        line = _canonical_json(event)
        with self._audit_lock:
            with self.audit_path.open("ab") as handle:
                handle.write(line)

    @staticmethod
    def _error(code: str, message: str, *, field: str | None = None) -> dict[str, Any]:
        error = ServiceError(code=code, message=message, field=field)
        return {"ok": False, "error": error.model_dump(mode="json")}

    def _finish(
        self, method: str, path: str, status: int, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        error_code = payload.get("error", {}).get("code") if payload.get("ok") is False else None
        self._audit(method=method, path=path, status=status, error_code=error_code)
        return status, payload

    def dispatch(
        self,
        method: str,
        target: str,
        *,
        body: bytes = b"",
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any]]:
        """Dispatch one HTTP-shaped request without opening a socket."""

        path = urlsplit(target).path or "/"
        method = method.upper()
        if len(body) > self.max_body_bytes:
            return self._finish(
                method,
                path,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                self._error("payload_too_large", "request payload exceeds the local limit"),
            )

        if method == "GET" and path == "/health":
            return self._finish(
                method, path, HTTPStatus.OK, self.application.health(self.readiness_run_dir)
            )
        if method == "GET" and path == "/ready":
            health = self.application.health(self.readiness_run_dir)
            payload = dict(health)
            payload["status"] = "ready" if health.get("status") == "healthy" else "not_ready"
            return self._finish(method, path, HTTPStatus.OK, payload)
        if method == "GET" and path == "/version":
            return self._finish(method, path, HTTPStatus.OK, self.application.version())
        if method == "GET" and path == "/openapi.json":
            return self._finish(method, path, HTTPStatus.OK, openapi_schema())
        if method != "POST" or path != "/v1/shadow/predictions":
            code = (
                "method_not_allowed"
                if path
                in {
                    "/health",
                    "/ready",
                    "/version",
                    "/openapi.json",
                    "/v1/shadow/predictions",
                }
                else "not_found"
            )
            status = _ERROR_STATUS[code]
            payload = self._error(code, "local API route is not available")
            return self._finish(method, path, status, payload)
        if not content_type.lower().split(";", 1)[0].strip() == "application/json":
            return self._finish(
                method,
                path,
                _ERROR_STATUS["unsupported_media_type"],
                self._error("unsupported_media_type", "application/json content is required"),
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._finish(
                method,
                path,
                HTTPStatus.BAD_REQUEST,
                self._error("invalid_request", "request body must be valid JSON"),
            )
        if not isinstance(payload, dict):
            return self._finish(
                method,
                path,
                HTTPStatus.BAD_REQUEST,
                self._error("invalid_request", "request body must be a JSON object"),
            )
        result = post_shadow_prediction(self.application, payload)
        if result.get("ok") is True:
            return self._finish(method, path, HTTPStatus.OK, result)
        error_code = str(result.get("error", {}).get("code", "blocked_provenance"))
        return self._finish(
            method,
            path,
            _ERROR_STATUS.get(error_code, HTTPStatus.SERVICE_UNAVAILABLE),
            result,
        )


class _RequestHandler(BaseHTTPRequestHandler):
    server: LocalAPIHTTPServer
    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        content = _canonical_json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _dispatch(self) -> None:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = max(0, int(length_header))
        except ValueError:
            length = self.server.api.max_body_bytes + 1
        body = self.rfile.read(min(length, self.server.api.max_body_bytes + 1))
        status, payload = self.server.api.dispatch(
            self.command,
            self.path,
            body=body,
            content_type=self.headers.get("Content-Type", ""),
        )
        self._respond(status, payload)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def log_message(self, format: str, *args: Any) -> None:
        return None


class LocalAPIHTTPServer(ThreadingHTTPServer):
    """HTTP server that can bind only to the loopback interface by default."""

    allow_reuse_address = True
    daemon_threads = True
    RequestHandlerClass: ClassVar[type[_RequestHandler]] = _RequestHandler

    def __init__(self, api: LocalServiceAPI, host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local API server must bind to loopback")
        super().__init__((host, port), self.RequestHandlerClass)
        self.api = api


__all__ = ["LocalAPIHTTPServer", "LocalServiceAPI", "openapi_schema"]
