from datetime import UTC, datetime, timedelta

import pytest

from football_prediction_lab.evaluation.odds_schema import OddsSnapshot
from football_prediction_lab.evaluation.source_policy import (
    SourceSelectionPolicy,
    apply_source_selection_policy,
)

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)


def snapshot(source: str, odds_type: str = "pre_match") -> OddsSnapshot:
    return OddsSnapshot(
        snapshot_id=f"{source}-{odds_type}",
        match_id="m-1",
        match_kickoff_utc=KICKOFF,
        market="btts",
        market_definition="Both teams to score at least one goal",
        selection="yes",
        decimal_odds=2.0,
        captured_at=KICKOFF - timedelta(hours=1),
        source_name=source,
        source_version="v1",
        provenance_id="p-1",
        input_sha256="c" * 64,
        odds_type=odds_type,
        is_licensed_or_reusable=True,
    )


def policy(**overrides: object) -> SourceSelectionPolicy:
    values: dict[str, object] = {
        "policy_id": "policy-1",
        "market": "btts",
        "source_name": "source-a",
        "odds_type": "pre_match",
        "declared_at": datetime(2025, 8, 1, 8, tzinfo=UTC),
    }
    values.update(overrides)
    return SourceSelectionPolicy(**values)


def test_policy_keeps_only_predeclared_source_and_type() -> None:
    result = apply_source_selection_policy(
        [snapshot("source-a"), snapshot("source-b"), snapshot("source-a", "closing")],
        policy(),
        kickoff_utc=KICKOFF,
    )
    assert [item.snapshot_id for item in result.accepted] == ["source-a-pre_match"]
    assert {row["reason"] for row in result.discarded_rows} == {
        "source_not_in_policy",
        "odds_type_not_in_policy",
    }


def test_policy_rejects_declaration_at_or_after_kickoff() -> None:
    with pytest.raises(ValueError, match="before kickoff"):
        apply_source_selection_policy(
            [snapshot("source-a")],
            policy(declared_at=KICKOFF),
            kickoff_utc=KICKOFF,
        )
    with pytest.raises(ValueError, match="closing"):
        policy(odds_type="closing")
