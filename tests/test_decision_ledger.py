from pathlib import Path

import pytest

from football_prediction_lab.evaluation.commercial_gate import GateDecision
from football_prediction_lab.evaluation.decision_ledger import (
    build_decision_ledger_event,
    write_decision_ledger,
)
from football_prediction_lab.evaluation.readiness import ReadinessDecision
from football_prediction_lab.evaluation.selection_provenance import SelectionProvenance


def decision() -> GateDecision:
    return GateDecision(
        accepted=True,
        prediction_id="pred-1",
        match_id="match-1",
        market="btts",
        selected_snapshot_ids=["snap-1"],
        reasons=[],
        protocol="latest_pre_match",
        market_implied_probability=0.5,
        overround=1.0,
        selection_provenance=SelectionProvenance(
            policy_id="policy-1",
            policy_sha256="a" * 64,
            snapshot_ids=["snap-1"],
            snapshot_fingerprints=["b" * 64],
            market="btts",
            source_name="source-a",
            odds_type="pre_match",
        ),
    )


def readiness() -> ReadinessDecision:
    return ReadinessDecision(
        status="conditional",
        rows=100,
        reasons=["descriptive_evidence_only"],
    )


def test_event_links_provenance_without_outcome_fields() -> None:
    event = build_decision_ledger_event("event-1", decision(), readiness())
    assert event.policy_sha256 == "a" * 64
    assert event.snapshot_fingerprints == ["b" * 64]
    assert event.financial_execution is False
    assert event.outcome_recorded is False
    assert "actual" not in event.model_dump()
    assert "roi" not in event.model_dump()


def test_ledger_write_is_deterministic_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    first = build_decision_ledger_event("event-b", decision(), readiness())
    second = build_decision_ledger_event("event-a", decision(), readiness())
    output = tmp_path / "ledger.jsonl"
    write_decision_ledger([first, second], output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert '"event_id": "event-a"' in lines[0]
    with pytest.raises(ValueError, match="unique"):
        write_decision_ledger([first, first], output)
