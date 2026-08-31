from datetime import UTC, datetime, timedelta

import pytest

from football_prediction_lab.nqbe_workflow import NQBEInput, NQBEResearchWorkflow

KICKOFF = datetime(2026, 8, 31, 20, tzinfo=UTC)


def payload(**overrides: object) -> NQBEInput:
    values: dict[str, object] = {
        "match_id": "fixture-1",
        "captured_at": KICKOFF - timedelta(minutes=30),
        "kickoff_at": KICKOFF,
        "odds_history": [2.1, 2.0, 1.9],
        "home_rate": 1.3,
        "away_rate": 1.0,
        "narrative_texts": ["strong form", "injury doubt"],
        "event_deltas": [0.1, 0.4, -0.1],
        "market_series": {"home": [2.1, 2.0, 1.9], "away": [3.0, 2.9, 2.8]},
        "information_scores": [0.1, 0.8, 0.2],
        "flow_scores": [0.2, 0.7, 0.3],
        "stress_body": 0.4,
        "stress_voice": 0.6,
        "historical_returns": [-0.1, 0.05, 0.1, -0.02],
    }
    values.update(overrides)
    return NQBEInput(**values)


def test_workflow_returns_complete_research_envelope() -> None:
    result = NQBEResearchWorkflow().run(payload())
    assert result.status == "research_only"
    assert result.research_only is True
    assert 0.0 <= result.btts_probability <= 1.0
    assert result.context_vector is not None
    assert result.quantum_anomaly is not None
    assert result.risk is not None
    assert result.manipulation is not None


def test_workflow_rejects_post_kickoff_capture() -> None:
    with pytest.raises(ValueError, match="strictly before"):
        NQBEResearchWorkflow().run(payload(captured_at=KICKOFF))


def test_workflow_is_deterministic_for_same_match() -> None:
    workflow = NQBEResearchWorkflow()
    assert workflow.run(payload()) == workflow.run(payload())
