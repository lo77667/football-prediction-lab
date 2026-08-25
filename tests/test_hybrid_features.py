from datetime import UTC, datetime

import pandas as pd
import pytest

from football_prediction_lab.features.hybrid import (
    HYBRID_FEATURE_COLUMNS,
    build_qualitative_features,
    merge_hybrid_features,
)
from football_prediction_lab.qualitative.contracts import QualitativeEvent


def make_event(event_id: str, match_id: str, hour: int, category: str) -> QualitativeEvent:
    return QualitativeEvent(
        event_id=event_id,
        match_id=match_id,
        available_at_utc=datetime(2024, 8, 10, hour, tzinfo=UTC),
        source_id="official-source",
        category=category,
        normalized_value={"status": "confirmed"},
        confidence=0.8,
        evidence="Archived source evidence",
    )


def test_hybrid_features_apply_match_specific_cutoff() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m1"],
            "kickoff_utc": ["2024-08-10T14:00:00Z"],
        }
    )
    events = [
        make_event("early", "m1", 13, "lineup"),
        make_event("late", "m1", 15, "injury"),
    ]

    result = build_qualitative_features(matches, events)

    row = result.iloc[0]
    assert row["qualitative_event_count_before"] == 1
    assert row["qualitative_lineup_count_before"] == 1
    assert row["qualitative_injury_count_before"] == 0
    assert set(HYBRID_FEATURE_COLUMNS).issubset(result.columns)


def test_hybrid_features_require_timezone_aware_cutoff() -> None:
    matches = pd.DataFrame({"match_id": ["m1"], "kickoff_utc": ["2024-08-10 14:00"]})
    with pytest.raises(ValueError, match="timezone-aware"):
        build_qualitative_features(matches, [])


def test_merge_fills_missing_qualitative_events_without_row_expansion() -> None:
    quantitative = pd.DataFrame({"match_id": ["m1", "m2"], "value": [1.0, 2.0]})
    qualitative = build_qualitative_features(
        pd.DataFrame(
            {
                "match_id": ["m1"],
                "kickoff_utc": ["2024-08-10T14:00:00Z"],
            }
        ),
        [],
    )

    result = merge_hybrid_features(quantitative, qualitative)

    assert len(result) == 2
    assert result.loc[result["match_id"] == "m2", "qualitative_event_count_before"].item() == 0
