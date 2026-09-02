from datetime import UTC, datetime, timedelta

import pytest

from football_prediction_lab.evaluation.odds_schema import OddsSnapshot
from football_prediction_lab.evaluation.selection_provenance import (
    build_selection_provenance,
    policy_sha256,
    verify_selection_provenance,
)
from football_prediction_lab.evaluation.source_policy import SourceSelectionPolicy

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)
CAPTURED = KICKOFF - timedelta(hours=1)


def policy() -> SourceSelectionPolicy:
    return SourceSelectionPolicy(
        policy_id="policy-1",
        market="btts",
        source_name="source-a",
        odds_type="pre_match",
        declared_at=KICKOFF - timedelta(hours=4),
    )


def snapshot(snapshot_id: str = "s-1") -> OddsSnapshot:
    return OddsSnapshot(
        snapshot_id=snapshot_id,
        match_id="m-1",
        match_kickoff_utc=KICKOFF,
        market="btts",
        market_definition="Both teams to score at least one goal",
        selection="yes",
        decimal_odds=2.0,
        captured_at=CAPTURED,
        source_name="source-a",
        source_version="v1",
        provenance_id="p-1",
        input_sha256="d" * 64,
        odds_type="pre_match",
        is_licensed_or_reusable=True,
    )


def test_bundle_contains_only_policy_and_snapshot_identity() -> None:
    bundle = build_selection_provenance(policy(), [snapshot()])
    assert len(bundle.policy_sha256) == 64
    assert bundle.snapshot_ids == ["s-1"]
    assert not hasattr(bundle, "actual")
    verify_selection_provenance(bundle, policy(), [snapshot()])


def test_bundle_rejects_policy_declared_after_capture() -> None:
    late_policy = policy().model_copy(update={"declared_at": CAPTURED + timedelta(minutes=1)})
    with pytest.raises(ValueError, match="no later"):
        build_selection_provenance(late_policy, [snapshot()])


def test_policy_hash_changes_when_precommit_changes() -> None:
    changed = policy().model_copy(update={"source_name": "source-b"})
    assert policy_sha256(policy()) != policy_sha256(changed)
