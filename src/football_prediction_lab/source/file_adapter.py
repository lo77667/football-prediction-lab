"""Deterministic local file source adapter for Cycle 46."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceRow:
    match_id: str
    market: str
    kickoff_utc: datetime
    observed_at_utc: datetime
    source_version: str


@dataclass(frozen=True)
class QuarantineRow:
    line_number: int
    reason: str


@dataclass(frozen=True)
class SourceBatch:
    rows: tuple[SourceRow, ...]
    quarantined: tuple[QuarantineRow, ...]
    input_sha256: str
    source_version: str


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("+00:00"):
        raise ValueError("timestamp must be explicit UTC")
    return datetime.fromisoformat(value)


class LocalJsonlSource:
    """Read-only source adapter; it never opens a network connection."""

    def __init__(self, path: Path, *, source_version: str, max_age_seconds: int = 86400) -> None:
        self.path = path
        self.source_version = source_version
        self.max_age_seconds = max_age_seconds

    def read(self, *, as_of_utc: datetime) -> SourceBatch:
        if (
            as_of_utc.tzinfo is None
            or as_of_utc.utcoffset() is None
            or as_of_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("as_of_utc must be explicit UTC")
        payload = self.path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        rows: list[SourceRow] = []
        quarantined: list[QuarantineRow] = []
        seen: set[tuple[str, str]] = set()
        for line_number, line in enumerate(payload.splitlines(), start=1):
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("row must be an object")
                if set(item) != {
                    "match_id",
                    "market",
                    "kickoff_utc",
                    "observed_at_utc",
                    "source_version",
                }:
                    raise ValueError("schema mismatch")
                if item["source_version"] != self.source_version:
                    raise ValueError("source version mismatch")
                match_id = item["match_id"]
                market = item["market"]
                if (
                    not isinstance(match_id, str)
                    or not match_id
                    or not isinstance(market, str)
                    or not market
                ):
                    raise ValueError("match identity is invalid")
                kickoff = _utc(item["kickoff_utc"])
                observed = _utc(item["observed_at_utc"])
                if kickoff <= as_of_utc:
                    raise ValueError("available_after_kickoff")
                age = (as_of_utc - observed).total_seconds()
                if age < 0 or age > self.max_age_seconds:
                    raise ValueError("stale_or_future_observation")
                key = (match_id, market)
                if key in seen:
                    raise ValueError("duplicate_match_market")
                seen.add(key)
                rows.append(SourceRow(match_id, market, kickoff, observed, self.source_version))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                quarantined.append(QuarantineRow(line_number, str(error)))
        rows.sort(key=lambda row: (row.kickoff_utc, row.match_id, row.market))
        return SourceBatch(tuple(rows), tuple(quarantined), digest, self.source_version)
