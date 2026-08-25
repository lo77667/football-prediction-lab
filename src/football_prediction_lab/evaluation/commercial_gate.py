"""Acceptance gate for auditable, pre-match model-versus-market comparisons."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from football_prediction_lab.evaluation.contracts import PredictionRecord
from football_prediction_lab.evaluation.odds_schema import (
    MatchReference,
    OddsSnapshot,
    audit_odds_snapshots,
    remove_binary_overround_from_snapshots,
)


class GateDecision(BaseModel):
    """Auditable result of the commercial evaluation acceptance gate."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    prediction_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    selected_snapshot_ids: list[str]
    reasons: list[str]
    protocol: Literal["opening", "latest_pre_match"]
    market_implied_probability: float | None = None
    overround: float | None = None


def gate_prediction_for_market_comparison(
    prediction: PredictionRecord,
    snapshots: list[OddsSnapshot],
    *,
    selection_protocol: Literal["opening", "latest_pre_match"] = "latest_pre_match",
    kickoff_tolerance_seconds: int = 60,
    holdout_seasons: set[str] | None = None,
    match_season: str | None = None,
) -> GateDecision:
    """Accept only a complete, binary, point-in-time market comparison."""

    protected = holdout_seasons or {"2526"}
    if match_season in protected:
        return GateDecision(
            accepted=False,
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            market=prediction.market,
            selected_snapshot_ids=[],
            reasons=["protected_holdout_season"],
            protocol=selection_protocol,
        )
    if prediction.market_definition.strip() == "":
        return GateDecision(
            accepted=False,
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            market=prediction.market,
            selected_snapshot_ids=[],
            reasons=["empty_market_definition"],
            protocol=selection_protocol,
        )

    relevant = [
        snapshot
        for snapshot in snapshots
        if snapshot.match_id == prediction.match_id
        and snapshot.market == prediction.market
    ]
    if not relevant:
        return GateDecision(
            accepted=False,
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            market=prediction.market,
            selected_snapshot_ids=[],
            reasons=["no_matching_market_snapshots"],
            protocol=selection_protocol,
        )
    reference = MatchReference(
        match_id=prediction.match_id,
        kickoff_utc=prediction.kickoff_utc,
        season=match_season or "unknown",
    )
    audit = audit_odds_snapshots(
        relevant,
        [reference],
        cutoff_utc=prediction.issued_at,
        expected_market_definitions={prediction.market: prediction.market_definition},
        kickoff_tolerance_seconds=kickoff_tolerance_seconds,
        selection_protocol=selection_protocol,
    )
    if len(audit.accepted) != 2:
        reasons = ["market_not_binary_after_selection"]
        reasons.extend(sorted(audit.summary["discarded_by_reason"]))
        return GateDecision(
            accepted=False,
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            market=prediction.market,
            selected_snapshot_ids=[snapshot.snapshot_id for snapshot in audit.accepted],
            reasons=reasons,
            protocol=selection_protocol,
        )
    normalized = remove_binary_overround_from_snapshots(audit.accepted)
    yes_index = next(
        (
            index
            for index, snapshot in enumerate(audit.accepted)
            if snapshot.selection.lower() == "yes"
        ),
        0,
    )
    fair_probability = normalized[
        "fair_probability_a" if yes_index == 0 else "fair_probability_b"
    ]
    return GateDecision(
        accepted=True,
        prediction_id=prediction.prediction_id,
        match_id=prediction.match_id,
        market=prediction.market,
        selected_snapshot_ids=[snapshot.snapshot_id for snapshot in audit.accepted],
        reasons=[],
        protocol=selection_protocol,
        market_implied_probability=float(fair_probability),
        overround=float(normalized["overround"]),
    )
