from __future__ import annotations

import json
import shutil
import socket
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from football_prediction_lab.ingestion.local_csv import ingest_file
from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.local_api import (
    LocalAPIHTTPServer,
    LocalServiceAPI,
    openapi_schema,
)
from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    SERVICE_VERSION,
    code_commit,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "cycle36_future_holdout_policy.json"
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
)
ATOMIC_RUN = (
    ROOT
    / "reports"
    / "generated"
    / "cycle_41_1_service_smoke"
    / "runs"
    / "356b08d69b859a1d30e24865196ac120aacb118679127d859f1f202e57ba2ec0"
)


def _prepare(tmp_path: Path) -> tuple[LocalServiceAPI, dict[str, Any]]:
    ingestion_root = tmp_path / "ingestion"
    result = ingest_file(
        FIXTURE_PATH,
        run_id="cycle42-api-input",
        output_root=ingestion_root,
        source_name="cycle42-test-local",
        source_version="cycle42-test-v1",
        license_or_usage_policy="test-only; no redistribution",
        season="2425",
        competition="EPL",
        code_commit=code_commit(ROOT),
        max_rejection_rate=1.0,
    )
    application = PredictionApplication(
        policy_path=POLICY_PATH,
        allowed_manifest_root=ingestion_root,
        output_root=tmp_path / "service-output",
        code_root=ROOT,
    )
    return LocalServiceAPI(application, audit_path=tmp_path / "audit.jsonl"), result.manifest


def _payload(manifest: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": "cycle42-test-001",
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "as_of_utc": "2025-01-01T12:00:00Z",
        "market": "btts",
        "policy_version": POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "expected_source_commit": code_commit(ROOT),
        "mode": "shadow",
    }
    payload.update(overrides)
    return payload


def _body(result: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    return result[1]


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {
            nested for child in value.values() for nested in _keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _keys(child)}
    return set()


def test_routes_return_safe_version_openapi_and_not_ready_without_artifacts(tmp_path: Path) -> None:
    api, _ = _prepare(tmp_path)
    assert api.dispatch("GET", "/health") == (
        200,
        {
            "status": "not_ready",
            "service_version": SERVICE_VERSION,
            "commercial_release": False,
        },
    )
    status, ready = api.dispatch("GET", "/ready")
    assert status == 200
    assert ready["status"] == "not_ready"
    status, version = api.dispatch("GET", "/version")
    assert status == 200
    assert version["service_version"] == SERVICE_VERSION
    assert version["commercial_release"] is False
    assert not any(str(value).startswith("/") for value in version.values())
    status, schema = api.dispatch("GET", "/openapi.json")
    assert status == 200
    assert set(schema["paths"]) == {
        "/health",
        "/ready",
        "/version",
        "/v1/shadow/predictions",
        "/openapi.json",
    }
    assert (
        schema["components"]["schemas"]["PredictionServiceRequest"]["additionalProperties"] is False
    )


def test_missing_ledger_cannot_be_ready(tmp_path: Path) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(ATOMIC_RUN, run_copy, dirs_exist_ok=True)
    (run_copy / "shadow_ledger.jsonl").unlink()
    api, _ = _prepare(tmp_path / "api")
    api.readiness_run_dir = run_copy
    api.application.allowed_manifest_root = run_copy.parent
    status, health = api.dispatch("GET", "/health")
    assert status == 200
    assert health["status"] == "blocked_provenance"
    assert api.dispatch("GET", "/ready")[1]["status"] == "not_ready"


def test_verified_atomic_run_is_ready_and_manifest_file_is_not(tmp_path: Path) -> None:
    api, _ = _prepare(tmp_path)
    api.readiness_run_dir = ATOMIC_RUN
    api.application.allowed_manifest_root = ATOMIC_RUN.parent
    status, health = api.dispatch("GET", "/health")
    assert status == 200
    assert health["status"] == "healthy"
    status, ready = api.dispatch("GET", "/ready")
    assert status == 200
    assert ready["status"] == "ready"
    api.readiness_run_dir = ATOMIC_RUN / "service_manifest.json"
    assert api.dispatch("GET", "/health")[1]["status"] == "blocked_provenance"


def test_shadow_prediction_is_prelabel_and_audited(tmp_path: Path) -> None:
    api, manifest = _prepare(tmp_path)
    status, result = api.dispatch(
        "POST",
        "/v1/shadow/predictions",
        body=json.dumps(_payload(manifest)).encode(),
        content_type="application/json; charset=utf-8",
    )
    assert status == 200
    assert result["ok"] is True
    response = result["response"]
    assert response["commercial_release"] is False
    assert len(response["predictions"]) == 3
    assert not _keys(response).intersection(
        {"target", "result", "odds", "roi", "ev", "stake", "home_goals", "away_goals"}
    )
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 1
    audit = json.loads(audit_lines[0])
    assert audit == {
        "commercial_release": False,
        "event": "local_api_request",
        "method": "POST",
        "path": "/v1/shadow/predictions",
        "status": 200,
    }


def test_duplicate_semantic_request_is_idempotent_across_request_ids(tmp_path: Path) -> None:
    api, manifest = _prepare(tmp_path)
    first = _body(
        api.dispatch(
            "POST",
            "/v1/shadow/predictions",
            body=json.dumps(_payload(manifest, request_id="one")).encode(),
        )
    )
    second = _body(
        api.dispatch(
            "POST",
            "/v1/shadow/predictions",
            body=json.dumps(_payload(manifest, request_id="two")).encode(),
        )
    )
    assert first["ok"] is True and second["ok"] is True
    assert first["response"]["request_fingerprint"] == second["response"]["request_fingerprint"]
    assert (
        first["response"]["response_content_sha256"]
        == second["response"]["response_content_sha256"]
    )
    assert second["response"]["operational_metrics"]["idempotent_replay"] is True


@pytest.mark.parametrize(
    ("extra_key", "extra_value"),
    [
        ("target", 1),
        ("result", "home_win"),
        ("odds", {"home": 2.0}),
        ("ev", 0.1),
        ("roi", 0.1),
        ("stake", 5),
        ("source_uri", "https://example.invalid/source.csv"),
        ("raw_csv", "match_id,home_team"),
        ("features", {"x": 1}),
    ],
)
def test_forbidden_raw_target_financial_and_source_fields_are_rejected(
    tmp_path: Path, extra_key: str, extra_value: Any
) -> None:
    api, manifest = _prepare(tmp_path)
    status, result = api.dispatch(
        "POST",
        "/v1/shadow/predictions",
        body=json.dumps(_payload(manifest, **{extra_key: extra_value})).encode(),
    )
    assert status == 400
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"
    assert "http" not in json.dumps(result).lower()


def test_path_traversal_version_mismatch_late_time_and_non_shadow_are_rejected(
    tmp_path: Path,
) -> None:
    api, manifest = _prepare(tmp_path)
    cases = [
        _payload(manifest, request_id="../escape"),
        _payload(manifest, expected_source_commit="0" * 40),
        _payload(manifest, as_of_utc="2025-01-02T00:00:00Z"),
        _payload(manifest, mode="live"),
    ]
    for payload in cases:
        status, result = api.dispatch(
            "POST", "/v1/shadow/predictions", body=json.dumps(payload).encode()
        )
        assert status in {400, 409}
        assert result["ok"] is False
        assert "/tmp" not in json.dumps(result)


def test_payload_content_type_json_and_routes_are_strict(tmp_path: Path) -> None:
    api, manifest = _prepare(tmp_path)
    status, result = api.dispatch(
        "POST",
        "/v1/shadow/predictions",
        body=json.dumps(_payload(manifest)).encode(),
        content_type="text/csv",
    )
    assert status == 415
    assert result["error"]["code"] == "unsupported_media_type"
    assert api.dispatch("GET", "/missing")[0] == 404
    assert api.dispatch("POST", "/health")[0] == 405
    assert api.dispatch("GET", "/v1/shadow/predictions")[0] == 405


def test_large_payload_and_malformed_json_are_rejected_without_raw_exception(
    tmp_path: Path,
) -> None:
    api, _ = _prepare(tmp_path)
    api.max_body_bytes = 8
    status, result = api.dispatch("POST", "/v1/shadow/predictions", body=b"{}" + b"x" * 20)
    assert status == 413
    assert result["error"]["code"] == "payload_too_large"
    api.max_body_bytes = 64 * 1024
    status, result = api.dispatch("POST", "/v1/shadow/predictions", body=b"not-json")
    assert status == 400
    assert result["error"]["code"] == "invalid_request"
    assert "traceback" not in json.dumps(result).lower()


def test_openapi_snapshot_is_deterministic_and_contains_no_sensitive_paths() -> None:
    assert openapi_schema() == openapi_schema()
    encoded = json.dumps(openapi_schema(), sort_keys=True).lower()
    assert "api_key" not in encoded
    assert "authorization" not in encoded
    assert "/home/ubuntu" not in encoded
    assert (
        openapi_schema()["components"]["schemas"]["PredictionServiceResponse"][
            "additionalProperties"
        ]
        is False
    )


def test_local_dispatch_does_not_open_external_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api, _ = _prepare(tmp_path)

    def blocked_connect(*_: Any, **__: Any) -> None:
        raise AssertionError("external network must not be used by local API dispatch")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    assert api.dispatch("GET", "/version")[0] == 200
    assert api.dispatch("GET", "/openapi.json")[0] == 200


def test_loopback_http_server_exposes_only_local_adapter(tmp_path: Path) -> None:
    api, _ = _prepare(tmp_path)
    server = LocalAPIHTTPServer(api, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", "/version")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
        assert response.status == 200
        assert payload["commercial_release"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_non_loopback_bind_is_rejected(tmp_path: Path) -> None:
    api, _ = _prepare(tmp_path)
    with pytest.raises(ValueError, match="loopback"):
        LocalAPIHTTPServer(api, host="0.0.0.0", port=0)
