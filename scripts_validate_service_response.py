"""Validate a local Cycle 41 service response and its Shadow Ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from football_prediction_lab.service.contracts import PredictionServiceResponse
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


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _forbidden_keys(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(_forbidden_keys(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_keys(child, f"{path}[{index}]"))
    return found


def _response_hash_payload(response: PredictionServiceResponse) -> dict[str, Any]:
    return {
        "service_version": response.service_version,
        "policy_version": response.policy_version,
        "model_version": response.model_version,
        "feature_version": response.feature_version,
        "manifest_fingerprint": response.manifest_fingerprint,
        "as_of_utc": response.as_of_utc.isoformat(),
        "predictions": [item.model_dump(mode="json") for item in response.predictions],
        "skipped": response.skipped,
    }


def validate_service_response(
    response_path: Path, ledger_path: Path | None = None
) -> dict[str, Any]:
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    forbidden = _forbidden_keys(payload)
    if forbidden:
        raise ValueError(f"service response contains forbidden keys: {forbidden}")
    response = PredictionServiceResponse.model_validate(payload)
    expected_hash = hashlib.sha256(_canonical_json(_response_hash_payload(response))).hexdigest()
    if response.response_content_sha256 != expected_hash:
        raise ValueError("response_content_sha256 mismatch")
    ledger_records = None
    if ledger_path is not None:
        ledger = ShadowLedger(ledger_path)
        ledger.verify()
        ledger_records = len(ledger.records())
    return {
        "validation": "passed",
        "response_content_sha256": response.response_content_sha256,
        "predictions_issued": len(response.predictions),
        "skipped_items": len(response.skipped),
        "ledger_records": ledger_records,
        "commercial_release": response.commercial_release,
        "forbidden_keys": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(validate_service_response(args.response, args.ledger), sort_keys=True, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
