"""Deterministic release governance for Cycle 47."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_STATES = {
    "not_ready",
    "shadow_only",
    "closed_beta",
    "commercial_information_service",
    "blocked_provenance",
    "blocked_model_quality",
    "blocked_operations",
}


@dataclass(frozen=True)
class GateDecision:
    state: str
    commercial_release: bool
    reasons: tuple[str, ...]
    checks: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "commercial_release": self.commercial_release,
            "reasons": list(self.reasons),
            "checks": dict(sorted(self.checks.items())),
        }


def evaluate_release_gate(
    checks: dict[str, bool], *, explicit_user_approval: bool = False
) -> GateDecision:
    checks = {str(key): bool(value) for key, value in checks.items()}
    reasons: list[str] = []
    if not checks.get("provenance_verified", False):
        reasons.append("provenance_not_verified")
        return GateDecision("blocked_provenance", False, tuple(reasons), checks)
    if not checks.get("model_quality_verified", False):
        reasons.append("model_quality_not_verified")
        return GateDecision("blocked_model_quality", False, tuple(reasons), checks)
    operational = (
        "worker_stable",
        "telegram_tested",
        "backup_restore_tested",
        "monitoring_ready",
        "security_reviewed",
    )
    missing_operations = [name for name in operational if not checks.get(name, False)]
    if missing_operations:
        reasons.extend(f"missing_{name}" for name in missing_operations)
        return GateDecision("blocked_operations", False, tuple(reasons), checks)
    if not checks.get("source_verified", False):
        reasons.append("authorized_live_source_missing")
        return GateDecision("not_ready", False, tuple(reasons), checks)
    if not checks.get("shadow_period_complete", False):
        reasons.append("shadow_period_incomplete")
        return GateDecision("shadow_only", False, tuple(reasons), checks)
    if not explicit_user_approval:
        reasons.append("explicit_user_approval_missing")
        return GateDecision("closed_beta", False, tuple(reasons), checks)
    if not checks.get("recipient_confirmed", False) or not checks.get("production_enabled", False):
        reasons.append("recipient_or_production_confirmation_missing")
        return GateDecision("closed_beta", False, tuple(reasons), checks)
    return GateDecision("commercial_information_service", True, tuple(), checks)


class KillSwitch:
    """File-backed local kill switch; absence or malformed content means stopped."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def is_stopped(self) -> bool:
        if not self.path.is_file():
            return True
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("stopped") is not False
        except (OSError, json.JSONDecodeError, AttributeError):
            return True

    def stop(self, reason: str = "manual") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"stopped": True, "reason": reason}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def resume(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text('{"stopped":false}\n', encoding="utf-8")
        os.replace(temporary, self.path)


__all__ = ["ALLOWED_STATES", "GateDecision", "KillSwitch", "evaluate_release_gate"]
