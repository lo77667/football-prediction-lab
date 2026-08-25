from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from football_prediction_lab.qualitative.contracts import (
    QualitativeEvent,
    QualitativeFeatureSet,
    filter_events_before_cutoff,
)
from football_prediction_lab.qualitative.io import load_events_jsonl

CUTOFF = datetime(2024, 8, 10, 14, 0, tzinfo=UTC)


def make_event(event_id: str, available_hour: int, *, match_id: str = "m1") -> QualitativeEvent:
    return QualitativeEvent(
        event_id=event_id,
        match_id=match_id,
        available_at_utc=datetime(2024, 8, 10, available_hour, tzinfo=UTC),
        observed_at_utc=datetime(2024, 8, 10, max(0, available_hour - 1), tzinfo=UTC),
        source_id="source-1",
        category="lineup",
        normalized_value={"home_confirmed": True},
        confidence=0.9,
        evidence="Official team announcement",
    )


def test_filter_events_by_availability_time() -> None:
    events = [make_event("late", 15), make_event("early", 13)]
    available = filter_events_before_cutoff(events, CUTOFF)
    assert [event.event_id for event in available] == ["early"]


def test_event_requires_a_source() -> None:
    with pytest.raises(ValidationError, match="source_url or source_id"):
        QualitativeEvent(
            event_id="e1",
            match_id="m1",
            available_at_utc=CUTOFF,
            category="news",
            normalized_value={"text": "x"},
            confidence=0.5,
            evidence="unreferenced note",
        )


def test_observed_time_cannot_follow_available_time() -> None:
    with pytest.raises(ValidationError, match="observed_at_utc"):
        QualitativeEvent(
            event_id="e1",
            match_id="m1",
            available_at_utc=datetime(2024, 8, 10, 13, tzinfo=UTC),
            observed_at_utc=datetime(2024, 8, 10, 14, tzinfo=UTC),
            source_id="source-1",
            category="injury",
            normalized_value={"player": "redacted", "status": "out"},
            confidence=0.8,
            evidence="Source excerpt",
        )


def test_feature_set_rejects_events_for_another_match() -> None:
    with pytest.raises(ValidationError, match="another match"):
        QualitativeFeatureSet(
            match_id="m1",
            cutoff_utc=CUTOFF,
            events=[make_event("wrong", 13, match_id="m2")],
        )


def test_jsonl_loader_rejects_duplicate_event_ids(tmp_path) -> None:
    event = make_event("duplicate", 13).model_dump_json()
    path = tmp_path / "events.jsonl"
    path.write_text(f"{event}\n{event}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate qualitative event_id"):
        load_events_jsonl(path)


def test_feature_set_returns_only_available_events() -> None:
    feature_set = QualitativeFeatureSet(
        match_id="m1",
        cutoff_utc=CUTOFF,
        events=[make_event("late", 15), make_event("early", 13)],
    )
    assert [event.event_id for event in feature_set.available_events()] == ["early"]
