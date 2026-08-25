from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from football_prediction_lab.evaluation.odds_benchmark import paired_bootstrap_comparison
from football_prediction_lab.evaluation.odds_schema import (
    MatchReference,
    OddsSnapshot,
    audit_odds_snapshots,
    remove_binary_overround_from_snapshots,
)

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)
MATCH = MatchReference(match_id="m-1", kickoff_utc=KICKOFF, season="2525")
DEFINITION = "Both teams to score at least one goal"


def snapshot(snapshot_id: str, selection: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "match_id": "m-1",
        "match_kickoff_utc": KICKOFF,
        "market": "btts",
        "market_definition": DEFINITION,
        "selection": selection,
        "decimal_odds": 2.0,
        "captured_at": KICKOFF - timedelta(minutes=30),
        "source_name": "fixture-source",
        "source_version": "v1",
        "provenance_id": "fixture-provenance",
        "input_sha256": "a" * 64,
        "odds_type": "pre_match",
        "is_licensed_or_reusable": True,
        "bookmaker_id": "fixture-bookmaker",
    }
    value.update(overrides)
    return value


def test_snapshot_requires_provenance_and_reusable_policy() -> None:
    with pytest.raises(ValidationError):
        OddsSnapshot(**snapshot("s-1", "yes", input_sha256="bad"))
    with pytest.raises(ValidationError):
        OddsSnapshot(**snapshot("s-1", "yes", is_licensed_or_reusable=False))


def test_audit_rejects_post_kickoff_unknown_and_kickoff_mismatch() -> None:
    result = audit_odds_snapshots(
        [
            snapshot("post", "yes", captured_at=KICKOFF),
            snapshot("unknown", "yes", match_id="missing"),
            snapshot(
                "mismatch",
                "yes",
                match_kickoff_utc=KICKOFF + timedelta(minutes=5),
            ),
        ],
        [MATCH],
    )
    reasons = {row["reason"] for row in result.discarded_rows}
    assert "captured_at_not_before_kickoff" in reasons
    assert "unknown_match_id" in reasons
    assert "kickoff_mismatch" in reasons
    assert result.summary["valid_snapshots"] == 0


def test_audit_keeps_latest_pre_match_and_rejects_closing_by_default() -> None:
    old = snapshot("old", "yes", captured_at=KICKOFF - timedelta(hours=2))
    latest = snapshot("latest", "yes", captured_at=KICKOFF - timedelta(minutes=10))
    closing = snapshot("closing", "no", odds_type="closing")
    result = audit_odds_snapshots(
        [old, latest, closing],
        [MATCH],
        expected_market_definitions={"btts": DEFINITION},
    )
    assert [item.snapshot_id for item in result.accepted] == ["latest"]
    assert "superseded_by_latest_pre_match" in {
        row["reason"] for row in result.discarded_rows
    }
    assert "odds_type_not_allowed:closing" in {
        row["reason"] for row in result.discarded_rows
    }


def test_audit_rejects_duplicate_outcome_and_market_definition_mismatch() -> None:
    duplicate = snapshot("same", "yes")
    result = audit_odds_snapshots(
        [duplicate, duplicate, snapshot("wrong", "no", market_definition="wrong")],
        [MATCH],
        expected_market_definitions={"btts": DEFINITION},
    )
    reasons = {row["reason"] for row in result.discarded_rows}
    assert "duplicate_outcome_in_snapshot" in reasons
    assert "market_definition_mismatch" in reasons


def test_binary_overround_rejects_non_binary_market_silently() -> None:
    yes = OddsSnapshot(**snapshot("yes", "yes"))
    no = OddsSnapshot(**snapshot("no", "no"))
    assert remove_binary_overround_from_snapshots([yes, no])["overround"] == 1.0
    with pytest.raises(ValueError, match="exactly two"):
        remove_binary_overround_from_snapshots([yes])


def test_paired_bootstrap_is_deterministic_and_match_scoped() -> None:
    frame = pd.DataFrame(
        {
            "match_id": [f"m-{index}" for index in range(12)],
            "model_probability": [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.2, 0.3, 0.7, 0.8],
            "market_implied_probability": [0.2] * 12,
            "actual": [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1],
            "baseline_probability": [0.5] * 12,
        }
    )
    first = paired_bootstrap_comparison(frame, n_resamples=100, seed=7)
    second = paired_bootstrap_comparison(frame, n_resamples=100, seed=7)
    assert first == second
    assert first["unit"] == "match_id"
    assert first["intervals"]["mean_raw_edge"] is not None
    assert first["match_rows"] == 12
