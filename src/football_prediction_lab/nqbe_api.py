"""Local JSON contract and append-only storage for NQBE research outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .nqbe_workflow import NQBEInput, NQBEResearchWorkflow


class NQBEAPI:
    """Pure in-process API adapter; callers provide all data and receive JSON-safe output."""

    def __init__(self, workflow: NQBEResearchWorkflow | None = None) -> None:
        self.workflow = workflow or NQBEResearchWorkflow()

    def post_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._request(payload)
        result = self.workflow.run(request)
        return {"ok": True, "research_only": True, "result": self._json_safe(asdict(result))}

    @staticmethod
    def _request(payload: dict[str, Any]) -> NQBEInput:
        if not isinstance(payload, dict):
            raise ValueError("NQBE request must be a JSON object")
        required = {
            "match_id",
            "captured_at",
            "kickoff_at",
            "odds_history",
            "home_rate",
            "away_rate",
        }
        missing = sorted(required.difference(payload))
        if missing:
            raise ValueError(f"missing NQBE request fields: {missing}")
        try:
            values = dict(payload)
            values["captured_at"] = datetime.fromisoformat(str(values["captured_at"]))
            values["kickoff_at"] = datetime.fromisoformat(str(values["kickoff_at"]))
            return NQBEInput(**values)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid NQBE request: {exc}") from exc

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): NQBEAPI._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [NQBEAPI._json_safe(item) for item in value]
        return value


class NQBEResearchLedger:
    """Append-only JSONL ledger with no overwrite or external side effects."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, response: dict[str, Any]) -> None:
        if response.get("research_only") is not True:
            raise ValueError("only research-only responses may be persisted")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


__all__ = ["NQBEAPI", "NQBEResearchLedger"]
