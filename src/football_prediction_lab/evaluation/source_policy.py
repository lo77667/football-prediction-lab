"""Predeclared market-source policy for provider-level comparisons."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from football_prediction_lab.evaluation.odds_schema import OddsSnapshot


class SourceSelectionPolicy(BaseModel):
    """A source and odds type selected before the relevant kickoff."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    policy_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    odds_type: str = Field(min_length=1)
    declared_at: AwareDatetime

    @model_validator(mode="after")
    def validate_odds_type(self) -> SourceSelectionPolicy:
        if self.odds_type not in {"opening", "pre_match"}:
            raise ValueError("source policy cannot select closing odds")
        return self


class SourcePolicyResult(BaseModel):
    """Accepted snapshots and explicit discards under a predeclared policy."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    accepted: list[OddsSnapshot]
    discarded_rows: list[dict[str, Any]]
    source_name: str
    odds_type: str


def apply_source_selection_policy(
    snapshots: list[OddsSnapshot],
    policy: SourceSelectionPolicy,
    *,
    kickoff_utc: datetime,
) -> SourcePolicyResult:
    """Filter without inspecting outcomes or selecting the best observed provider."""

    if kickoff_utc.tzinfo is None or kickoff_utc.utcoffset() is None:
        raise ValueError("kickoff_utc must be timezone-aware")
    kickoff = kickoff_utc.astimezone(UTC)
    if policy.declared_at >= kickoff:
        raise ValueError("source policy must be declared before kickoff")

    accepted: list[OddsSnapshot] = []
    discarded: list[dict[str, str]] = []
    for snapshot in snapshots:
        if snapshot.market != policy.market:
            discarded.append(
                {"snapshot_id": snapshot.snapshot_id, "reason": "market_not_in_policy"}
            )
            continue
        if snapshot.source_name != policy.source_name:
            discarded.append(
                {"snapshot_id": snapshot.snapshot_id, "reason": "source_not_in_policy"}
            )
            continue
        if snapshot.odds_type != policy.odds_type:
            discarded.append(
                {"snapshot_id": snapshot.snapshot_id, "reason": "odds_type_not_in_policy"}
            )
            continue
        if snapshot.captured_at >= kickoff:
            discarded.append(
                {"snapshot_id": snapshot.snapshot_id, "reason": "captured_at_not_before_kickoff"}
            )
            continue
        if snapshot.captured_at < policy.declared_at:
            discarded.append(
                {"snapshot_id": snapshot.snapshot_id, "reason": "captured_before_policy"}
            )
            continue
        accepted.append(snapshot)
    accepted.sort(key=lambda item: (item.captured_at, item.snapshot_id))
    return SourcePolicyResult(
        policy_id=policy.policy_id,
        accepted=accepted,
        discarded_rows=discarded,
        source_name=policy.source_name,
        odds_type=policy.odds_type,
    )
