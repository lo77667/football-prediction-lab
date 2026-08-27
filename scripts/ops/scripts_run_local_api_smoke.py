"""Run a deterministic loopback smoke for the Cycle 42 local API."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import shutil
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from football_prediction_lab.ingestion.local_csv import ingest_file
from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.artifact_validation import (
    sha256_file,
    validate_service_response,
)
from football_prediction_lab.service.local_api import LocalAPIHTTPServer, LocalServiceAPI
from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    code_commit,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "cycle36_future_holdout_policy.json"
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
)


def _canonical_json(value: Any) -> bytes:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (content + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_canonical_json(value))


def _request_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": "cycle42-local-api-smoke",
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "as_of_utc": "2025-01-01T12:00:00Z",
        "market": "btts",
        "policy_version": POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "expected_source_commit": code_commit(ROOT),
        "mode": "shadow",
    }


def _call(
    connection: HTTPConnection, method: str, path: str, payload: Any = None
) -> tuple[int, dict[str, Any]]:
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "reports" / "generated" / "cycle_42_local_api_smoke",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    workspace_root = output_root.parent / f".{output_root.name}.workspace"
    shutil.rmtree(workspace_root, ignore_errors=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    atexit.register(shutil.rmtree, workspace_root, ignore_errors=True)
    ingestion_root = workspace_root / "ingestion"
    result = ingest_file(
        FIXTURE_PATH,
        run_id="cycle42-local-api-input",
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
        output_root=workspace_root / "service-output",
        code_root=ROOT,
    )
    # Cycle 42 smoke does not trust a previous-cycle run for readiness.
    # A caller may provide a verified run to LocalServiceAPI directly in tests.
    audit_path = output_root / "audit.jsonl"
    api = LocalServiceAPI(
        application,
        readiness_run_dir=None,
        audit_path=audit_path,
    )
    server = LocalAPIHTTPServer(api)
    thread = threading.Thread(target=server.serve_forever, name="cycle42-local-api", daemon=True)
    thread.start()
    request_payload = _request_payload(result.manifest)
    connection = HTTPConnection(server.server_address[0], server.server_address[1], timeout=10)
    try:
        health_status, health = _call(connection, "GET", "/health")
        ready_status, ready = _call(connection, "GET", "/ready")
        version_status, version = _call(connection, "GET", "/version")
        openapi_status, openapi = _call(connection, "GET", "/openapi.json")
        prediction_status, prediction = _call(
            connection,
            "POST",
            "/v1/shadow/predictions",
            request_payload,
        )
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    if prediction.get("ok") is not True:
        raise RuntimeError("local API smoke prediction did not succeed")
    request_path = output_root / "service_request.json"
    response_path = output_root / "service_response.json"
    ledger_path = output_root / "shadow_ledger.jsonl"
    manifest_path = output_root / "service_manifest.json"
    validation_path = output_root / "validation.json"
    _write_json(request_path, request_payload)
    _write_json(response_path, prediction["response"])
    source_ledger_path = workspace_root / "service-output" / "ledger" / "predictions.jsonl"
    shutil.copyfile(source_ledger_path, ledger_path)
    validation = validate_service_response(response_path, ledger_path)
    manifest = {
        "schema_version": "cycle42-local-api-manifest-v1",
        "api_contract_version": "cycle42-local-api-v1",
        "request_fingerprint": prediction["response"]["request_fingerprint"],
        "request_sha256": sha256_file(request_path),
        "source_manifest_fingerprint": result.manifest["manifest_fingerprint"],
        "code_commit": prediction["response"]["code_commit"],
        "policy_version": prediction["response"]["policy_version"],
        "model_version": prediction["response"]["model_version"],
        "feature_version": prediction["response"]["feature_version"],
        "as_of_utc": prediction["response"]["as_of_utc"],
        "response_content_sha256": prediction["response"]["response_content_sha256"],
        "response_sha256": sha256_file(response_path),
        "ledger_sha256": sha256_file(ledger_path),
        "ledger_records_count": validation["ledger_records"],
        "commercial_release": False,
    }
    _write_json(manifest_path, manifest)
    validation.update(
        {
            "api_contract_version": "cycle42-local-api-v1",
            "manifest_artifact_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "commercial_release": False,
        }
    )
    _write_json(validation_path, validation)

    summary = {
        "health": {"status": health_status, "payload": health},
        "ready": {"status": ready_status, "payload": ready},
        "version": {"status": version_status, "payload": version},
        "openapi": {
            "status": openapi_status,
            "openapi": openapi.get("openapi"),
            "path_count": len(openapi.get("paths", {})),
        },
        "prediction": {
            "status": prediction_status,
            "ok": prediction.get("ok"),
            "predictions_count": len(prediction.get("response", {}).get("predictions", [])),
            "commercial_release": prediction.get("response", {}).get("commercial_release"),
        },
        "audit_path": "audit.jsonl",
        "artifacts": {
            "request": "service_request.json",
            "response": "service_response.json",
            "manifest": "service_manifest.json",
            "ledger": "shadow_ledger.jsonl",
            "validation": "validation.json",
        },
        "network_scope": "loopback-only",
        "commercial_release": False,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
