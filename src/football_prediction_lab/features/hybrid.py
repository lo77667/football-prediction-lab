"""Leakage-safe aggregation of source-backed qualitative events."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import pandas as pd

from football_prediction_lab.qualitative.contracts import (
    QualitativeEvent,
    filter_events_before_cutoff,
)

QUALITATIVE_CATEGORIES = (
    "injury",
    "suspension",
    "lineup",
    "news",
    "referee_context",
    "match_importance",
    "weather",
    "other",
)
HYBRID_FEATURE_COLUMNS = [
    "qualitative_event_count_before",
    "qualitative_confidence_mean_before",
    *[f"qualitative_{category}_count_before" for category in QUALITATIVE_CATEGORIES],
]


def build_qualitative_features(
    matches: pd.DataFrame,
    events: Iterable[QualitativeEvent],
    *,
    cutoff_column: str = "kickoff_utc",
) -> pd.DataFrame:
    """Aggregate only source-backed events available before each match kickoff."""

    required = {"match_id", cutoff_column}
    missing = required.difference(matches.columns)
    if missing:
        raise ValueError(f"Missing hybrid match columns: {sorted(missing)}")

    ordered = matches.sort_values([cutoff_column, "match_id"]).reset_index(drop=True)
    by_match: dict[str, list[QualitativeEvent]] = {}
    for event in events:
        by_match.setdefault(event.match_id, []).append(event)

    rows: list[dict[str, object]] = []
    for row in ordered.itertuples(index=False):
        cutoff = getattr(row, cutoff_column)
        cutoff = _as_aware_datetime(cutoff)
        available = filter_events_before_cutoff(by_match.get(row.match_id, []), cutoff)
        record: dict[str, object] = {
            "match_id": row.match_id,
            "qualitative_event_count_before": len(available),
            "qualitative_confidence_mean_before": (
                sum(event.confidence for event in available) / len(available)
                if available
                else 0.0
            ),
        }
        for category in QUALITATIVE_CATEGORIES:
            record[f"qualitative_{category}_count_before"] = sum(
                event.category == category for event in available
            )
        rows.append(record)
    return pd.DataFrame(rows)


def merge_hybrid_features(
    quantitative: pd.DataFrame,
    qualitative: pd.DataFrame,
) -> pd.DataFrame:
    """Merge qualitative aggregates onto quantitative rows without changing row count."""

    if quantitative["match_id"].duplicated().any():
        raise ValueError("quantitative match_id values must be unique")
    if qualitative["match_id"].duplicated().any():
        raise ValueError("qualitative match_id values must be unique")
    merged = quantitative.merge(
        qualitative,
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    for column in HYBRID_FEATURE_COLUMNS:
        merged[column] = merged[column].fillna(0.0)
    return merged


def _as_aware_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("match cutoff must be timezone-aware")
    return timestamp.to_pydatetime()
