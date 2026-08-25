"""Controlled qualitative feature extraction for coach notes.

This module is intentionally conservative. It does not diagnose psychological state and
it does not treat generic sentiment as a proxy for performance. It emits reviewable
marker events with evidence references and explicit missingness.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

import pandas as pd

from football_prediction_lab.player_warehouse.contracts import (
    QualitativeMarkerEvent,
    QualitativeTrait,
)

_MARKER_PATTERNS: dict[QualitativeTrait, tuple[re.Pattern[str], ...]] = {
    "confidence": (
        re.compile(r"\b(low|lacked|lacking|reduced)\s+confidence\b", re.I),
        re.compile(r"\b(confident|confidence)\b", re.I),
    ),
    "communication": (
        re.compile(r"\b(communicat(?:e|ed|es|ing)|vocal|organis(?:e|ed|es|ing))\b", re.I),
    ),
    "coachability": (
        re.compile(r"\b(coachab(?:le|ility)|responded\s+well\s+to\s+feedback)\b", re.I),
    ),
    "attention": (
        re.compile(r"\b(focus(?:ed)?|concentration|attentive|switched\s+off)\b", re.I),
    ),
    "recovery_mindset": (
        re.compile(r"\b(recover(?:y|ed|ing)|bounced\s+back|resilience|resilient)\b", re.I),
    ),
    "competitive_response": (
        re.compile(r"\b(competi(?:tive|tion)|responded\s+after|reaction\s+to\s+setback)\b", re.I),
    ),
    "readiness": (
        re.compile(r"\b(ready|readiness|prepared|preparedness)\b", re.I),
    ),
}

_NEGATION_RE = re.compile(r"\b(no|not|without|never|didn't|did not|shows no signs of)\b", re.I)
_LOW_RE = re.compile(r"\b(low|lacked|lacking|reduced|poor|struggled|struggle)\b", re.I)
_HIGH_RE = re.compile(r"\b(high|strong|good|excellent|confident|ready|prepared|resilient)\b", re.I)


def extract_marker_events(
    *,
    note_id: str,
    player_id: str,
    text: str,
    observed_at_utc: datetime,
    available_at_utc: datetime,
    source_id: str,
    taxonomy_version: str = "psych_markers_v1",
    review_status: str = "not_reviewed",
) -> list[QualitativeMarkerEvent]:
    """Extract conservative marker events from a note.

    Each event retains an evidence span. Negated mentions are excluded rather than
    converted into a false positive. Ambiguous phrases receive lower confidence.
    """

    if not text.strip():
        return []
    events: list[QualitativeMarkerEvent] = []
    for trait, patterns in _MARKER_PATTERNS.items():
        for pattern in patterns:
            if any(event.trait == trait for event in events):
                break
            for match in pattern.finditer(text):
                start = max(0, match.start() - 45)
                end = min(len(text), match.end() + 45)
                evidence = text[start:end].strip()
                prefix = text[max(0, match.start() - 35) : match.start()]
                if _NEGATION_RE.search(prefix):
                    continue
                if _LOW_RE.search(evidence):
                    value, direction = -0.6, "low"
                elif _HIGH_RE.search(evidence):
                    value, direction = 0.7, "high"
                else:
                    value, direction = 0.0, "neutral"
                confidence = 0.72 if direction != "neutral" else 0.52
                if "may" in evidence.lower() or "might" in evidence.lower():
                    confidence -= 0.15
                events.append(
                    QualitativeMarkerEvent(
                        event_id=f"{note_id}:{trait}:{match.start()}",
                        player_id=player_id,
                        trait=trait,
                        value=value,
                        confidence=max(0.0, min(1.0, confidence)),
                        observed_at_utc=observed_at_utc,
                        available_at_utc=available_at_utc,
                        evidence_ref=evidence,
                        source_id=source_id,
                        taxonomy_version=taxonomy_version,
                        review_status=review_status,  # type: ignore[arg-type]
                    )
                )
                break
    return events


def aggregate_marker_features(
    events: Iterable[QualitativeMarkerEvent],
    *,
    player_id: str,
    cutoff_utc: datetime,
    recency_lambda: float = 0.08,
) -> pd.DataFrame:
    """Aggregate eligible events into a one-row-per-trait feature table.

    The output includes event count, weighted value, confidence, recency, and an
    explicit missingness flag. No event appearing after ``cutoff_utc`` can enter
    the result.
    """

    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    if recency_lambda < 0:
        raise ValueError("recency_lambda must be non-negative")

    grouped: dict[str, list[QualitativeMarkerEvent]] = defaultdict(list)
    for event in events:
        if event.player_id == player_id and event.is_eligible_at(cutoff_utc):
            grouped[event.trait].append(event)

    rows: list[dict[str, object]] = []
    traits = tuple(_MARKER_PATTERNS)
    for trait in traits:
        eligible = grouped.get(trait, [])
        if not eligible:
            rows.append(
                {
                    "player_id": player_id,
                    "cutoff_utc": cutoff_utc,
                    "trait": trait,
                    "feature_value": float("nan"),
                    "event_count": 0,
                    "mean_extraction_confidence": float("nan"),
                    "days_since_last_observation": float("nan"),
                    "is_missing": True,
                }
            )
            continue
        weights: list[float] = []
        for event in eligible:
            age_days = max(0.0, (cutoff_utc - event.observed_at_utc).total_seconds() / 86400)
            weights.append(math.exp(-recency_lambda * age_days))
        total_weight = sum(weights)
        last_observed = max(event.observed_at_utc for event in eligible)
        rows.append(
            {
                "player_id": player_id,
                "cutoff_utc": cutoff_utc,
                "trait": trait,
                "feature_value": (
                    sum(event.value * weight for event, weight in zip(eligible, weights))
                    / total_weight
                ),
                "event_count": len(eligible),
                "mean_extraction_confidence": (
                    sum(event.confidence for event in eligible) / len(eligible)
                ),
                "days_since_last_observation": max(
                    0.0, (cutoff_utc - last_observed).total_seconds() / 86400
                ),
                "is_missing": False,
            }
        )
    return pd.DataFrame(rows)
