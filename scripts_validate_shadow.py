"""Validate Cycle 39 shadow artifacts, ledger integrity, and pre-match safety invariants."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.shadow.contracts import ShadowPrediction, ShadowRun  # noqa: E402
from football_prediction_lab.shadow.ledger import ShadowLedger  # noqa: E402

FORBIDDEN_KEYS = {
    "target",
    "result",
    "btts",
    "total_yellows_over_3_5",
    "home_goals",
    "away_goals",
    "home_yellows",
    "away_yellows",
    "fthg",
    "ftag",
    "ftr",
}


def _forbidden_keys(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(_forbidden_keys(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_keys(child, f"{path}[{index}]"))
    return found


def validate_shadow_artifacts(
    predictions_path: Path, run_path: Path, ledger_path: Path
) -> dict[str, Any]:
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    forbidden = _forbidden_keys(predictions)
    if forbidden:
        raise ValueError(f"shadow artifact contains target/post-match keys: {forbidden}")
    if (
        predictions.get("commercial_release") is not False
        or run.get("commercial_release") is not False
    ):
        raise ValueError("shadow artifacts must have commercial_release=false")
    records = [ShadowPrediction.model_validate(item) for item in predictions["predictions"]]
    if len(records) != run["predictions_issued"]:
        raise ValueError("prediction count does not match run artifact")
    if run["output_sha256"] != hashlib.sha256(predictions_path.read_bytes()).hexdigest():
        raise ValueError("prediction artifact SHA-256 does not match run artifact")
    validated_run = ShadowRun.model_validate(run)
    ledger = ShadowLedger(ledger_path)
    ledger.verify()
    if ledger.sha256() != validated_run.ledger_sha256:
        raise ValueError("ledger SHA-256 does not match run artifact")
    ledger_records = ledger.records()
    if len(ledger_records) != len(records):
        raise ValueError("ledger record count does not match prediction count")
    prediction_ids = [record.prediction_id for record in records]
    ledger_ids = [str(entry["record_id"]) for entry in ledger_records]
    if prediction_ids != ledger_ids:
        raise ValueError("ledger order or prediction IDs do not match artifact")
    return {
        "validation": "passed",
        "predictions_path": str(predictions_path.resolve()),
        "run_path": str(run_path.resolve()),
        "ledger_path": str(ledger_path.resolve()),
        "run_id": validated_run.run_id,
        "predictions_issued": len(records),
        "rows_skipped": validated_run.rows_skipped,
        "output_sha256": validated_run.output_sha256,
        "ledger_sha256": validated_run.ledger_sha256,
        "commercial_release": validated_run.commercial_release,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            validate_shadow_artifacts(args.predictions, args.run, args.ledger),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
