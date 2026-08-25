"""Tamper-evident append-only prediction ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from football_prediction_lab.contracts import OutcomeRecord, PredictionRecord


class PredictionLedger:
    """JSONL ledger with a hash chain and immutable prediction identifiers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_prediction(self, record: PredictionRecord) -> str:
        return self._append("prediction", record.model_dump(mode="json"), record.prediction_id)

    def append_outcome(self, record: OutcomeRecord) -> str:
        if not self._has_prediction(record.prediction_id):
            raise ValueError("outcome cannot be recorded before its prediction")
        return self._append("outcome", record.model_dump(mode="json"), record.prediction_id)

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def verify(self) -> None:
        previous_hash = "GENESIS"
        seen_predictions: set[str] = set()
        for entry in self.records():
            if entry["prev_hash"] != previous_hash:
                raise ValueError("ledger hash chain is broken")
            payload = {
                "record_type": entry["record_type"],
                "record": entry["record"],
                "record_id": entry["record_id"],
                "prev_hash": entry["prev_hash"],
            }
            expected_hash = _hash_payload(payload)
            if entry["record_hash"] != expected_hash:
                raise ValueError("ledger record hash is invalid")
            if entry["record_type"] == "prediction":
                if entry["record_id"] in seen_predictions:
                    raise ValueError("duplicate prediction id in ledger")
                seen_predictions.add(entry["record_id"])
            previous_hash = entry["record_hash"]

    def _append(self, record_type: str, record: dict[str, Any], record_id: str) -> str:
        self.verify()
        if record_type == "prediction" and self._has_prediction(record_id):
            raise ValueError(f"prediction already exists: {record_id}")
        entries = self.records()
        previous_hash = entries[-1]["record_hash"] if entries else "GENESIS"
        payload = {
            "record_type": record_type,
            "record": record,
            "record_id": record_id,
            "prev_hash": previous_hash,
        }
        entry = {**payload, "record_hash": _hash_payload(payload)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry["record_hash"]

    def _has_prediction(self, prediction_id: str) -> bool:
        return any(
            entry["record_type"] == "prediction" and entry["record_id"] == prediction_id
            for entry in self.records()
        )


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
