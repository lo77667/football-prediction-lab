"""Persistence helpers for source-backed qualitative events."""

from __future__ import annotations

import json
from pathlib import Path

from football_prediction_lab.qualitative.contracts import QualitativeEvent


def load_events_jsonl(path: Path) -> list[QualitativeEvent]:
    """Load one strict QualitativeEvent JSON object per line."""

    events: list[QualitativeEvent] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = QualitativeEvent.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid qualitative event at line {line_number}") from exc
        if event.event_id in seen_ids:
            raise ValueError(f"duplicate qualitative event_id: {event.event_id}")
        seen_ids.add(event.event_id)
        events.append(event)
    return events
