"""Fail-closed validation for one atomic Cycle 41.1 service run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from football_prediction_lab.service.contracts import (
    PredictionServiceRequest,
    PredictionServiceResponse,
)
from football_prediction_lab.shadow.ledger import ShadowLedger

FORBIDDEN_KEYS = {
    "target",
    "result",
    "odds",
    "roi",
    "ev",
    "stake",
    "home_goals",
    "away_goals",
    "fthg",
    "ftag",
    "ftr",
}


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def forbidden_keys(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(forbidden_keys(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_keys(child, f"{path}[{index}]"))
    return found


def request_fingerprint(request: PredictionServiceRequest) -> str:
    semantic = request.model_dump(mode="json", exclude={"request_id"})
    return sha256_bytes(canonical_json(semantic))


def response_hash_payload(response: PredictionServiceResponse) -> dict[str, Any]:
    metrics = response.operational_metrics.model_dump(mode="json")
    metrics.pop("idempotent_replay", None)
    return {
        "request_fingerprint": response.request_fingerprint,
        "code_commit": response.code_commit,
        "service_version": response.service_version,
        "policy_version": response.policy_version,
        "model_version": response.model_version,
        "feature_version": response.feature_version,
        "manifest_fingerprint": response.manifest_fingerprint,
        "as_of_utc": response.as_of_utc.isoformat(),
        "predictions": [item.model_dump(mode="json") for item in response.predictions],
        "skipped": response.skipped,
        "operational_metrics": metrics,
    }


def response_content_sha256(response: PredictionServiceResponse) -> str:
    return sha256_bytes(canonical_json(response_hash_payload(response)))


def _required_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} file is missing or is not a regular file")
    return path


def validate_service_response(
    response_path: Path, ledger_path: Path | None = None
) -> dict[str, Any]:
    """Validate response and require a real ledger whenever records are declared."""

    response_file = _required_file(response_path, "response")
    payload = json.loads(response_file.read_text(encoding="utf-8"))
    forbidden = forbidden_keys(payload)
    if forbidden:
        raise ValueError(f"service response contains forbidden keys: {forbidden}")
    response = PredictionServiceResponse.model_validate(payload)
    expected_response_hash = response_content_sha256(response)
    if response.response_content_sha256 != expected_response_hash:
        raise ValueError("response_content_sha256 mismatch")
    declared_records = response.operational_metrics.ledger_records
    if declared_records > 0 and ledger_path is None:
        raise FileNotFoundError("ledger is required when response declares ledger records")
    ledger_records = None
    ledger_markets: list[str] = []
    if ledger_path is not None:
        ledger_file = _required_file(ledger_path, "ledger")
        ledger = ShadowLedger(ledger_file)
        ledger.verify()
        entries = ledger.records()
        ledger_records = len(entries)
        if ledger_records != declared_records:
            raise ValueError("ledger record count does not match response metrics")
        if ledger.sha256() != response.operational_metrics.ledger_sha256:
            raise ValueError("ledger SHA-256 does not match response metrics")
        ledger_ids = [str(entry["record_id"]) for entry in entries]
        response_ids = [item.prediction_id for item in response.predictions]
        if not set(response_ids).issubset(set(ledger_ids)):
            raise ValueError("response prediction IDs are absent from ledger")
        ledger_markets = sorted(
            {
                str(entry["record"].get("market"))
                for entry in entries
                if entry.get("record", {}).get("market") in {"btts", "cards"}
            }
        )
        if ledger_markets != response.operational_metrics.ledger_markets:
            raise ValueError("ledger markets do not match response metrics")
    return {
        "validation": "passed",
        "response_content_sha256": response.response_content_sha256,
        "predictions_issued": len(response.predictions),
        "skipped_items": len(response.skipped),
        "ledger_records": ledger_records,
        "ledger_markets": ledger_markets,
        "commercial_release": response.commercial_release,
        "forbidden_keys": [],
    }


def validate_service_run(run_dir: Path) -> dict[str, Any]:
    """Validate the six files of one atomic service run directory."""

    root = run_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError("service run directory is missing")
    request_path = _required_file(root / "service_request.json", "service request")
    response_path = _required_file(root / "service_response.json", "service response")
    manifest_path = _required_file(root / "service_manifest.json", "service manifest")
    ledger_path = _required_file(root / "shadow_ledger.jsonl", "shadow ledger")
    predictions_path = _required_file(root / "predictions_prelabel.jsonl", "prediction artifact")
    request = PredictionServiceRequest.model_validate(
        json.loads(request_path.read_text(encoding="utf-8"))
    )
    response = PredictionServiceResponse.model_validate(
        json.loads(response_path.read_text(encoding="utf-8"))
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    response_result = validate_service_response(response_path, ledger_path)
    prediction_lines = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    forbidden = forbidden_keys(prediction_lines)
    if forbidden:
        raise ValueError(f"prediction artifact contains forbidden keys: {forbidden}")
    ledger = ShadowLedger(ledger_path)
    ledger.verify()
    ledger_entries = ledger.records()
    prediction_payloads = [
        item.get("prediction", item) if isinstance(item, dict) else item
        for item in prediction_lines
    ]
    if any(not isinstance(item, dict) or "prediction" not in item for item in prediction_lines):
        raise ValueError("prediction artifact records must carry service provenance envelope")
    prediction_ids = [str(item.get("prediction_id")) for item in prediction_payloads]
    ledger_ids = [str(entry["record_id"]) for entry in ledger_entries]
    if prediction_ids != ledger_ids:
        raise ValueError("prediction artifact IDs do not match ledger order")
    expected_request_fp = request_fingerprint(request)
    expected_request_sha = sha256_file(request_path)
    expected_response_sha = sha256_file(response_path)
    expected_ledger_sha = sha256_file(ledger_path)
    expected_prediction_sha = sha256_file(predictions_path)
    prediction_feature_versions = sorted(
        {str(item.get("feature_version")) for item in prediction_payloads}
    )
    prediction_model_versions = sorted(
        {str(item.get("model_version")) for item in prediction_payloads}
    )
    expected = {
        "run_fingerprint": expected_request_fp,
        "request_fingerprint": expected_request_fp,
        "request_sha256": expected_request_sha,
        "response_sha256": expected_response_sha,
        "response_content_sha256": response.response_content_sha256,
        "ledger_sha256": expected_ledger_sha,
        "prediction_artifact_sha256": expected_prediction_sha,
        "source_manifest_fingerprint": response.manifest_fingerprint,
        "as_of_utc": response.as_of_utc.isoformat(),
        "predictions_count": len(prediction_lines),
        "response_predictions_count": len(response.predictions),
        "ledger_records_count": len(ledger_entries),
        "code_commit": response.code_commit,
        "policy_version": request.policy_version,
        "model_version": request.model_version,
        "feature_version": request.feature_version,
        "prediction_feature_versions": prediction_feature_versions,
        "prediction_model_versions": prediction_model_versions,
        "prediction_artifact_code_commit": response.code_commit,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"service manifest mismatch: {key}")
    if response.operational_metrics.ledger_records != len(ledger_entries):
        raise ValueError("response and ledger counts differ")
    if response.request_fingerprint != expected_request_fp:
        raise ValueError("request fingerprint does not match request artifact")
    if response.code_commit != manifest.get("code_commit"):
        raise ValueError("response code commit does not match service manifest")
    if response.policy_version != manifest.get("policy_version"):
        raise ValueError("response policy version does not match service manifest")
    if response.model_version != manifest.get("model_version"):
        raise ValueError("response model version does not match service manifest")
    if response.feature_version != manifest.get("feature_version"):
        raise ValueError("response feature version does not match service manifest")
    if response.operational_metrics.response_predictions_count != len(response.predictions):
        raise ValueError("response prediction count mismatch")
    if response.operational_metrics.ledger_prediction_count != len(ledger_entries):
        raise ValueError("ledger prediction count mismatch")
    for envelope, item in zip(prediction_lines, prediction_payloads, strict=True):
        if envelope.get("code_commit") != response.code_commit:
            raise ValueError("prediction code commit mismatch")
        if envelope.get("request_fingerprint") != expected_request_fp:
            raise ValueError("prediction request fingerprint mismatch")
        if envelope.get("as_of_utc") != response.as_of_utc.isoformat():
            raise ValueError("prediction as_of mismatch")
        if item.get("policy_version") != request.policy_version:
            raise ValueError("prediction policy version mismatch")
        if item.get("model_version") not in manifest.get("prediction_model_versions", []):
            raise ValueError("prediction model version mismatch")
        if item.get("feature_version") not in manifest.get("prediction_feature_versions", []):
            raise ValueError("prediction feature version mismatch")
        if item.get("source_manifest_fingerprint") != response.manifest_fingerprint:
            raise ValueError("prediction source manifest mismatch")
    if manifest.get("commercial_release") is not False:
        raise ValueError("service manifest requires commercial_release=false")
    if response.code_commit != manifest.get("code_commit"):
        raise ValueError("response and manifest code commits differ")
    if response.request_fingerprint != manifest.get("request_fingerprint"):
        raise ValueError("response and manifest request fingerprints differ")
    if response.operational_metrics.ledger_sha256 != expected_ledger_sha:
        raise ValueError("response ledger SHA differs from ledger file")
    return {
        "validation": "passed",
        "run_fingerprint": expected_request_fp,
        "request_fingerprint": expected_request_fp,
        "response_content_sha256": response.response_content_sha256,
        "response_sha256": expected_response_sha,
        "ledger_sha256": expected_ledger_sha,
        "predictions_count": len(prediction_lines),
        "response_predictions_count": len(response.predictions),
        "ledger_records_count": len(ledger_entries),
        "commercial_release": False,
        **response_result,
    }
