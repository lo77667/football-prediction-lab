"""Deterministic, metadata-only quality profiling for accepted odds snapshots."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from football_prediction_lab.evaluation.odds_schema import (
    OddsSnapshot,
    canonical_snapshot_key,
)


class OddsQualityProfile(BaseModel):
    """Auditable quality summary; contains no outcomes or financial quantities."""

    model_config = ConfigDict(extra="forbid")

    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: int = Field(ge=0)
    unique_matches: int = Field(ge=0)
    duplicate_identity_rows: int = Field(ge=0)
    market_source_groups: int = Field(ge=0)
    capture_min_utc: str | None = None
    capture_max_utc: str | None = None
    non_monotonic_match_captures: int = Field(ge=0)


def verify_quality_profile(
    snapshots: Iterable[OddsSnapshot],
    expected: OddsQualityProfile,
) -> OddsQualityProfile:
    """Recompute and fail closed when a stored quality profile no longer matches."""

    actual = profile_odds_quality(snapshots)
    if actual != expected:
        raise ValueError("odds quality profile does not match accepted snapshots")
    return actual


def profile_odds_quality(snapshots: Iterable[OddsSnapshot]) -> OddsQualityProfile:
    """Profile accepted snapshots deterministically, without inspecting outcomes."""

    rows = list(snapshots)
    identities = [canonical_snapshot_key(snapshot) for snapshot in rows]
    duplicate_rows = len(identities) - len(set(identities))
    captures_by_match: dict[str, list[object]] = defaultdict(list)
    for snapshot in rows:
        captures_by_match[snapshot.match_id].append(snapshot.captured_at.astimezone(UTC))
    non_monotonic = sum(
        1
        for captures in captures_by_match.values()
        if captures != sorted(captures)
    )
    captures = [snapshot.captured_at.astimezone(UTC) for snapshot in rows]
    groups = {(item.market, item.source_name) for item in rows}
    body = {
        "rows": len(rows),
        "unique_matches": len({item.match_id for item in rows}),
        "duplicate_identity_rows": duplicate_rows,
        "market_source_groups": len(groups),
        "capture_min_utc": min(captures).isoformat() if captures else None,
        "capture_max_utc": max(captures).isoformat() if captures else None,
        "non_monotonic_match_captures": non_monotonic,
    }
    digest = sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return OddsQualityProfile(profile_sha256=digest, **body)
