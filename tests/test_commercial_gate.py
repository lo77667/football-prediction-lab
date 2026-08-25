from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from football_prediction_lab.evaluation.commercial_gate import (
    gate_prediction_for_market_comparison,
)
from football_prediction_lab.evaluation.commercial_report import (
    assert_no_protected_holdout,
    build_grouped_market_report,
)
from football_prediction_lab.evaluation.contracts import PredictionRecord
from football_prediction_lab.evaluation.odds_schema import OddsSnapshot

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)
ISSUED = datetime(2025, 8, 1, 10, tzinfo=UTC)
DEFINITION = "Both teams to score at least one goal"


def prediction() -> PredictionRecord:
    return PredictionRecord(
        prediction_id="p-1",
        market="btts",
        market_definition=DEFINITION,
        match_id="m-1",
        issued_at=ISSUED,
        kickoff_utc=KICKOFF,
        probability=0.6,
        model_version="v1",
        feature_version="f1",
        training_cutoff=datetime(2025, 7, 31, tzinfo=UTC),
        input_provenance=["manifest-1"],
    )


def odds(selection: str, snapshot_id: str, **overrides: object) -> OddsSnapshot:
    values: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "match_id": "m-1",
        "match_kickoff_utc": KICKOFF,
        "market": "btts",
        "market_definition": DEFINITION,
        "selection": selection,
        "decimal_odds": 2.0,
        "captured_at": ISSUED - timedelta(minutes=10),
        "source_name": "fixture-source",
        "source_version": "v1",
        "provenance_id": "fixture-provenance",
        "input_sha256": "b" * 64,
        "odds_type": "pre_match",
        "is_licensed_or_reusable": True,
    }
    values.update(overrides)
    return OddsSnapshot(**values)


def test_gate_accepts_complete_binary_pre_match_market() -> None:
    result = gate_prediction_for_market_comparison(
        prediction(), [odds("yes", "yes"), odds("no", "no")]
    )
    assert result.accepted is True
    assert result.market_implied_probability == 0.5
    assert result.overround == 1.0
    assert result.reasons == []


def test_gate_rejects_snapshot_after_prediction_issue_time() -> None:
    result = gate_prediction_for_market_comparison(
        prediction(),
        [
            odds("yes", "yes", captured_at=ISSUED + timedelta(minutes=1)),
            odds("no", "no", captured_at=ISSUED + timedelta(minutes=1)),
        ],
    )
    assert result.accepted is False
    assert "captured_at_not_before_cutoff" in result.reasons


def test_gate_rejects_closing_and_protected_holdout() -> None:
    closing_result = gate_prediction_for_market_comparison(
        prediction(),
        [odds("yes", "yes", odds_type="closing"), odds("no", "no", odds_type="closing")],
    )
    assert closing_result.accepted is False
    holdout_result = gate_prediction_for_market_comparison(
        prediction(), [odds("yes", "yes"), odds("no", "no")], match_season="2526"
    )
    assert holdout_result.accepted is False
    assert holdout_result.reasons == ["protected_holdout_season"]


def test_grouped_report_is_descriptive_and_rejects_holdout() -> None:
    frame = pd.DataFrame(
        {
            "match_id": [f"m-{index}" for index in range(12)],
            "season": ["2425"] * 12,
            "market": ["btts"] * 12,
            "odds_type": ["pre_match"] * 12,
            "source": ["fixture-source"] * 12,
            "model_probability": [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.2, 0.3, 0.7, 0.8],
            "market_implied_probability": [0.5] * 12,
            "actual": [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1],
            "baseline_probability": [0.5] * 12,
        }
    )
    report = build_grouped_market_report(frame, n_resamples=100, seed=3)
    assert report["financial_execution"] is False
    assert report["groups"][0]["uncertainty"]["unit"] == "match_id"
    assert_no_protected_holdout(frame)
    frame.loc[0, "season"] = "2526"
    with pytest.raises(ValueError, match="protected"):
        assert_no_protected_holdout(frame)


def test_gate_rejects_market_definition_mismatch() -> None:
    result = gate_prediction_for_market_comparison(
        prediction(),
        [
            odds("yes", "yes", market_definition="different"),
            odds("no", "no", market_definition="different"),
        ],
    )
    assert result.accepted is False
    assert "market_definition_mismatch" in result.reasons
