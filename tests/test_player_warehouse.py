from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from football_prediction_lab.player_warehouse.alerts import build_high_risk_alerts
from football_prediction_lab.player_warehouse.contracts import QualitativeMarkerEvent
from football_prediction_lab.player_warehouse.ingest import (
    canonical_sha256,
    make_receipt,
    quarantine,
)
from football_prediction_lab.player_warehouse.modeling import (
    evaluate_ablation,
    temporal_holdout_indices,
)
from football_prediction_lab.player_warehouse.qualitative import (
    aggregate_marker_features,
    extract_marker_events,
)


def test_high_risk_alert_builder_detects_pattern_and_is_idempotency_ready() -> None:
    summary = pd.DataFrame(
        {
            "player_id": ["p-1", "p-2"],
            "activity_date": ["2026-08-25", "2026-08-25"],
            "player_load_au": [180.0, 180.0],
            "prior_28_observation_load_avg": [100.0, 100.0],
            "confidence_score": [-0.6, 0.2],
            "qualitative_score_missing": [False, False],
        }
    )
    alerts = build_high_risk_alerts(summary, alert_date=date(2026, 8, 25))
    assert len(alerts) == 1
    assert alerts.loc[0, "player_id"] == "p-1"
    assert alerts.loc[0, "dedupe_key"] == "p-1|2026-08-25|high_load_low_confidence"
    assert alerts.loc[0, "severity"] == "high"


def test_high_risk_alert_builder_suppresses_missing_baseline_or_score() -> None:
    summary = pd.DataFrame(
        {
            "player_id": ["p-1", "p-2"],
            "activity_date": ["2026-08-25", "2026-08-25"],
            "player_load_au": [180.0, 180.0],
            "prior_28_observation_load_avg": [None, 100.0],
            "confidence_score": [-0.6, None],
            "qualitative_score_missing": [True, True],
        }
    )
    assert build_high_risk_alerts(summary).empty


def test_alert_thresholds_are_validated() -> None:
    summary = pd.DataFrame(
        {
            "player_id": ["p-1"],
            "activity_date": ["2026-08-25"],
            "player_load_au": [180.0],
            "prior_28_observation_load_avg": [100.0],
            "confidence_score": [-0.6],
            "qualitative_score_missing": [False],
        }
    )
    with pytest.raises(ValueError, match="between -1 and 0"):
        build_high_risk_alerts(summary, confidence_threshold=0.2)


def test_ingestion_hash_is_order_independent_and_quarantine_is_safe() -> None:
    first = {"player_id": "p-1", "value": 1, "nested": {"b": 2, "a": 3}}
    second = {"nested": {"a": 3, "b": 2}, "value": 1, "player_id": "p-1"}
    assert canonical_sha256(first) == canonical_sha256(second)
    receipt = make_receipt(
        source_system="coach_notes",
        source_record_id="n-1",
        payload=first,
    )
    record = quarantine(
        source_system="coach_notes",
        source_record_id="n-1",
        payload=first,
        reason="schema_error",
    )
    assert receipt.source_sha256 == record.payload_sha256
    assert not hasattr(record, "payload")


def test_marker_extractor_preserves_evidence_and_skips_negation() -> None:
    events = extract_marker_events(
        note_id="n-1",
        player_id="p-1",
        text="Low confidence after conceding early, but no signs of low confidence in training.",
        observed_at_utc=datetime(2026, 8, 20, 18, tzinfo=UTC),
        available_at_utc=datetime(2026, 8, 20, 20, tzinfo=UTC),
        source_id="coach-note-1",
    )
    confidence_events = [event for event in events if event.trait == "confidence"]
    assert len(confidence_events) == 1
    assert confidence_events[0].value < 0
    assert "Low confidence" in confidence_events[0].evidence_ref


def test_marker_contract_rejects_late_availability() -> None:
    with pytest.raises(ValueError, match="available_at_utc"):
        QualitativeMarkerEvent(
            event_id="e-1",
            player_id="p-1",
            trait="confidence",
            value=0.2,
            confidence=0.8,
            observed_at_utc=datetime(2026, 8, 20, 20, tzinfo=UTC),
            available_at_utc=datetime(2026, 8, 20, 19, tzinfo=UTC),
            evidence_ref="note",
            source_id="s-1",
            taxonomy_version="v1",
        )


def test_aggregate_uses_cutoff_and_exposes_missingness() -> None:
    events = [
        QualitativeMarkerEvent(
            event_id="early",
            player_id="p-1",
            trait="confidence",
            value=-0.6,
            confidence=0.9,
            observed_at_utc=datetime(2026, 8, 20, 10, tzinfo=UTC),
            available_at_utc=datetime(2026, 8, 20, 11, tzinfo=UTC),
            evidence_ref="low confidence",
            source_id="s-1",
            taxonomy_version="v1",
            review_status="coach_reviewed",
        ),
        QualitativeMarkerEvent(
            event_id="late",
            player_id="p-1",
            trait="confidence",
            value=0.8,
            confidence=0.9,
            observed_at_utc=datetime(2026, 8, 20, 12, tzinfo=UTC),
            available_at_utc=datetime(2026, 8, 20, 20, tzinfo=UTC),
            evidence_ref="confident",
            source_id="s-1",
            taxonomy_version="v1",
            review_status="coach_reviewed",
        ),
    ]
    result = aggregate_marker_features(
        events,
        player_id="p-1",
        cutoff_utc=datetime(2026, 8, 20, 15, tzinfo=UTC),
    )
    confidence = result.loc[result["trait"] == "confidence"].iloc[0]
    readiness = result.loc[result["trait"] == "readiness"].iloc[0]
    assert confidence["event_count"] == 1
    assert confidence["feature_value"] < 0
    assert bool(readiness["is_missing"]) is True


def test_temporal_holdout_is_ordered_and_non_overlapping() -> None:
    cutoffs = pd.Series(pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC"))
    train, test = temporal_holdout_indices(cutoffs, test_fraction=0.2)
    assert set(train).isdisjoint(set(test))
    assert max(train) < min(test)


def test_hybrid_ablation_returns_two_evaluations() -> None:
    rng = np.random.default_rng(42)
    n = 40
    cutoffs = pd.Series(pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"))
    quantitative = pd.DataFrame({"sprint_30m_s": rng.normal(5.0, 0.2, n)})
    qualitative = pd.DataFrame({"confidence": rng.normal(0.0, 0.5, n)})
    y = np.array([0, 1] * (n // 2))
    results = evaluate_ablation(quantitative, qualitative, y, cutoffs, test_fraction=0.25)
    assert [result.model_name for result in results] == ["quantitative_only", "hybrid"]
    assert all(result.n_train == 30 and result.n_test == 10 for result in results)
