"""Auditable provenance bundles for predeclared source selection."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from football_prediction_lab.evaluation.odds_schema import (
    OddsSnapshot,
    canonical_snapshot_fingerprint,
)
from football_prediction_lab.evaluation.source_policy import SourceSelectionPolicy


class SelectionProvenance(BaseModel):
    """Metadata-only provenance for a selected market source and snapshot set."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_ids: list[str] = Field(min_length=1)
    snapshot_fingerprints: list[str] = Field(min_length=1)
    market: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    odds_type: str = Field(min_length=1)


def policy_sha256(policy: SourceSelectionPolicy) -> str:
    """Hash canonical policy JSON, excluding no fields and without runtime timestamps."""

    payload = policy.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_selection_provenance(
    policy: SourceSelectionPolicy,
    snapshots: list[OddsSnapshot],
) -> SelectionProvenance:
    """Create metadata-only evidence that selection was policy-locked before capture."""

    if not snapshots:
        raise ValueError("at least one selected snapshot is required")
    if any(snapshot.market != policy.market for snapshot in snapshots):
        raise ValueError("all snapshots must match the policy market")
    if any(snapshot.source_name != policy.source_name for snapshot in snapshots):
        raise ValueError("all snapshots must match the policy source")
    if any(snapshot.odds_type != policy.odds_type for snapshot in snapshots):
        raise ValueError("all snapshots must match the policy odds type")
    if any(policy.declared_at > snapshot.captured_at for snapshot in snapshots):
        raise ValueError("policy must be declared no later than every snapshot capture")
    return SelectionProvenance(
        policy_id=policy.policy_id,
        policy_sha256=policy_sha256(policy),
        snapshot_ids=[snapshot.snapshot_id for snapshot in snapshots],
        snapshot_fingerprints=[canonical_snapshot_fingerprint(snapshot) for snapshot in snapshots],
        market=policy.market,
        source_name=policy.source_name,
        odds_type=policy.odds_type,
    )


def verify_selection_provenance(
    bundle: SelectionProvenance,
    policy: SourceSelectionPolicy,
    snapshots: list[OddsSnapshot],
) -> None:
    """Fail closed if policy or selected snapshot identity changed after report creation."""

    expected = build_selection_provenance(policy, snapshots)
    if bundle != expected:
        raise ValueError("selection provenance does not match policy and snapshots")
