from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from football_prediction_lab.shadow.contracts import ShadowPrediction


class ShadowLedger:
    """Append-only JSONL ledger for immutable shadow predictions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def verify(self) -> None:
        previous_hash = "GENESIS"
        seen_ids: set[str] = set()
        for entry in self.records():
            if entry.get("prev_hash") != previous_hash:
                raise ValueError("shadow ledger hash chain is broken")
            payload = {
                "record_type": entry.get("record_type"),
                "record": entry.get("record"),
                "record_id": entry.get("record_id"),
                "prev_hash": entry.get("prev_hash"),
            }
            if _hash_payload(payload) != entry.get("record_hash"):
                raise ValueError("shadow ledger record hash is invalid")
            if entry.get("record_type") != "prediction":
                raise ValueError("shadow ledger contains unsupported record type")
            record_id = str(entry.get("record_id"))
            if record_id in seen_ids:
                raise ValueError("shadow ledger contains duplicate prediction ID")
            seen_ids.add(record_id)
            previous_hash = str(entry["record_hash"])

    def append_prediction(self, prediction: ShadowPrediction) -> str:
        self.verify()
        payload = prediction.model_dump(mode="json")
        existing = {
            str(entry["record_id"]): entry
            for entry in self.records()
            if entry.get("record_type") == "prediction"
        }
        if prediction.prediction_id in existing:
            entry = existing[prediction.prediction_id]
            if entry.get("record") != payload:
                raise ValueError("prediction ID conflict: existing record would be mutated")
            return str(entry["record_hash"])
        entries = self.records()
        previous_hash = entries[-1]["record_hash"] if entries else "GENESIS"
        record = {
            "record_type": "prediction",
            "record": payload,
            "record_id": prediction.prediction_id,
            "prev_hash": previous_hash,
        }
        entry = {**record, "record_hash": _hash_payload(record)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return str(entry["record_hash"])

    def sha256(self) -> str:
        if not self.path.exists():
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
