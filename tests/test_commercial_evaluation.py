from datetime import UTC, datetime

import numpy as np
import pytest

from football_prediction_lab.evaluation.benchmarks import (
    constant_historical_rate,
    last_n_historical_rate,
    remove_binary_overround,
    theoretical_edge_and_ev,
)
from football_prediction_lab.evaluation.contracts import OddsProvenance, PredictionRecord
from football_prediction_lab.evaluation.metrics import evaluate_binary_extended


def _prediction(**overrides: object) -> PredictionRecord:
    values: dict[str, object] = {
        "prediction_id": "p-1",
        "market": "btts",
        "market_definition": "Both teams to score at least one goal",
        "match_id": "m-1",
        "issued_at": datetime(2025, 8, 1, 10, tzinfo=UTC),
        "kickoff_utc": datetime(2025, 8, 1, 12, tzinfo=UTC),
        "probability": 0.6,
        "threshold": 0.5,
        "model_version": "model-v1",
        "feature_version": "features-v1",
        "training_cutoff": datetime(2025, 7, 31, 23, tzinfo=UTC),
        "input_provenance": ["manifest-sha256"],
    }
    values.update(overrides)
    return PredictionRecord(**values)


def test_binary_overround_is_normalized() -> None:
    result = remove_binary_overround(2.0, 2.0)
    assert result["overround"] == 1.0
    assert result["fair_a"] == 0.5
    assert result["fair_b"] == 0.5


def test_historical_benchmarks_use_only_supplied_history() -> None:
    assert constant_historical_rate([0, 1, 1]) == pytest.approx(2 / 3)
    assert last_n_historical_rate([0, 1, 1, 0], 2) == 0.5


def test_theoretical_economic_metrics_are_descriptive_only() -> None:
    result = theoretical_edge_and_ev(0.6, 2.0, commission=0.1)
    assert result["implied_probability"] == 0.5
    assert result["raw_edge"] == pytest.approx(0.1)
    assert result["theoretical_expected_value"] == pytest.approx(0.14)


def test_extended_metrics_include_discrimination_and_skill_scores() -> None:
    result = evaluate_binary_extended(
        probabilities=np.array([0.1, 0.3, 0.7, 0.9]),
        actual=np.array([0, 0, 1, 1]),
        baseline_probability=0.5,
        expected_rows=4,
    )
    assert result["roc_auc"] == 1.0
    assert result["average_precision"] == 1.0
    assert result["brier_skill_score"] > 0
    assert result["log_loss_skill_score"] > 0
    assert result["coverage"] == 1.0
    assert result["calibration_slope"] is not None


def test_extended_metrics_fallback_for_single_class() -> None:
    result = evaluate_binary_extended([0.2, 0.3], [0, 0], baseline_probability=0.5)
    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["calibration_slope"] is None


def test_prediction_rejects_probability_after_kickoff_and_unknown_definition() -> None:
    with pytest.raises(ValueError, match="issued_at"):
        _prediction(issued_at=datetime(2025, 8, 1, 12, tzinfo=UTC))
    with pytest.raises(ValueError, match="market_definition"):
        _prediction(market_definition="unknown")


def test_prediction_rejects_odds_after_kickoff() -> None:
    odds = OddsProvenance(
        decimal_odds=2.0,
        odds_timestamp=datetime(2025, 8, 1, 13, tzinfo=UTC),
        source="test-only fixture",
        market_type="binary",
        provenance_id="fixture-1",
    )
    with pytest.raises(ValueError, match="odds_timestamp"):
        _prediction(odds=odds)
