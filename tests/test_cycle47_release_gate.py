from __future__ import annotations

import json
from pathlib import Path

from football_prediction_lab.release import KillSwitch, evaluate_release_gate

BASE = {
    "provenance_verified": True,
    "model_quality_verified": True,
    "worker_stable": True,
    "telegram_tested": True,
    "backup_restore_tested": True,
    "monitoring_ready": True,
    "security_reviewed": True,
    "source_verified": False,
    "shadow_period_complete": False,
    "recipient_confirmed": False,
    "production_enabled": False,
}


def test_missing_source_is_not_ready_and_never_commercial() -> None:
    decision = evaluate_release_gate(BASE)
    assert decision.state == "not_ready"
    assert decision.commercial_release is False
    assert "authorized_live_source_missing" in decision.reasons


def test_unverified_provenance_blocks_before_other_states() -> None:
    checks = {**BASE, "provenance_verified": False, "source_verified": True}
    decision = evaluate_release_gate(checks)
    assert decision.state == "blocked_provenance"
    assert decision.commercial_release is False


def test_missing_quality_blocks() -> None:
    decision = evaluate_release_gate({**BASE, "model_quality_verified": False})
    assert decision.state == "blocked_model_quality"


def test_missing_operations_block() -> None:
    decision = evaluate_release_gate({**BASE, "monitoring_ready": False})
    assert decision.state == "blocked_operations"
    assert "missing_monitoring_ready" in decision.reasons


def test_shadow_and_closed_beta_remain_noncommercial() -> None:
    shadow = evaluate_release_gate({**BASE, "source_verified": True})
    assert shadow.state == "shadow_only"
    assert shadow.commercial_release is False
    closed = evaluate_release_gate(
        {**BASE, "source_verified": True, "shadow_period_complete": True}
    )
    assert closed.state == "closed_beta"
    assert closed.commercial_release is False


def test_even_all_checks_need_explicit_approval_and_flags() -> None:
    checks = {**BASE, "source_verified": True, "shadow_period_complete": True}
    assert evaluate_release_gate(checks).state == "closed_beta"
    approved = evaluate_release_gate(
        {**checks, "recipient_confirmed": True, "production_enabled": True},
        explicit_user_approval=True,
    )
    assert approved.state == "commercial_information_service"
    assert approved.commercial_release is True


def test_kill_switch_defaults_to_stopped_and_writes_atomically(tmp_path: Path) -> None:
    switch = KillSwitch(tmp_path / "kill_switch.json")
    assert switch.is_stopped() is True
    switch.resume()
    assert switch.is_stopped() is False
    switch.stop("test")
    assert switch.is_stopped() is True
    payload = json.loads((tmp_path / "kill_switch.json").read_text(encoding="utf-8"))
    assert payload == {"reason": "test", "stopped": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_malformed_kill_switch_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    path.write_text("not-json", encoding="utf-8")
    assert KillSwitch(path).is_stopped() is True
