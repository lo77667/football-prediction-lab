"""Audit-only decision events for commercial gate and readiness outcomes."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from football_prediction_lab.evaluation.commercial_gate import GateDecision
from football_prediction_lab.evaluation.readiness import ReadinessDecision


class DecisionLedgerEvent(BaseModel):
    """A non-financial event that contains no post-match result fields."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    prediction_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    gate_accepted: bool
    readiness_status: str = Field(min_length=1)
    reasons: list[str]
    policy_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    snapshot_fingerprints: list[str]
    financial_execution: bool = False
    outcome_recorded: bool = False

    @field_validator("reasons")
    @classmethod
    def reject_financial_claims(cls, reasons: list[str]) -> list[str]:
        prohibited = {"roi", "stake", "profit", "wager", "bet", "odds recommendation"}
        if any(
            any(term in reason.casefold() for term in prohibited) for reason in reasons
        ):
            raise ValueError("decision ledger cannot contain financial claims")
        return reasons


def build_decision_ledger_event(
    event_id: str,
    decision: GateDecision,
    readiness: ReadinessDecision,
) -> DecisionLedgerEvent:
    """Create a ledger event from decisions without accepting target/outcome input."""

    provenance = decision.selection_provenance
    return DecisionLedgerEvent(
        event_id=event_id,
        prediction_id=decision.prediction_id,
        match_id=decision.match_id,
        market=decision.market,
        gate_accepted=decision.accepted,
        readiness_status=readiness.status,
        reasons=[*decision.reasons, *readiness.reasons],
        policy_sha256=provenance.policy_sha256 if provenance else None,
        snapshot_fingerprints=provenance.snapshot_fingerprints if provenance else [],
    )


def write_decision_ledger(
    events: list[DecisionLedgerEvent],
    path: Path,
) -> None:
    """Write deterministic JSONL and reject duplicate event identifiers."""

    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("decision ledger event_id values must be unique")
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(events, key=lambda event: event.event_id)
    path.write_text(
        "".join(
            json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n"
            for event in ordered
        ),
        encoding="utf-8",
    )
