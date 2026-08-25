"""Strict, provenance-first contracts for pre-match odds snapshots."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

OddsType = Literal["opening", "pre_match", "closing"]


class MatchReference(BaseModel):
    """Minimal trusted match identity used for deterministic odds joins."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    match_id: str = Field(min_length=1)
    kickoff_utc: AwareDatetime
    season: str = Field(min_length=1)


class OddsSnapshot(BaseModel):
    """One source-backed decimal price captured at a declared point in time."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    snapshot_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    match_kickoff_utc: AwareDatetime
    market: str = Field(min_length=1)
    market_definition: str = Field(min_length=1)
    selection: str = Field(min_length=1)
    decimal_odds: float = Field(gt=1.0)
    captured_at: AwareDatetime
    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    provenance_id: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    odds_type: OddsType
    is_licensed_or_reusable: bool
    bookmaker_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_policy_fields(self) -> OddsSnapshot:
        if not self.market_definition.strip():
            raise ValueError("market_definition must be explicit")
        if not self.is_licensed_or_reusable:
            raise ValueError("odds snapshot is not licensed or reusable")
        return self


class OddsAuditResult(BaseModel):
    """Serializable audit result with accepted snapshots and explicit discard reasons."""

    model_config = ConfigDict(extra="forbid")

    accepted: list[OddsSnapshot]
    discarded_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _discard(snapshot_id: str | None, reason: str) -> dict[str, str | None]:
    return {"snapshot_id": snapshot_id, "reason": reason}


def audit_odds_snapshots(
    raw_snapshots: list[dict[str, Any] | OddsSnapshot],
    matches: list[MatchReference],
    *,
    cutoff_utc: datetime | None = None,
    allowed_odds_types: set[OddsType] | None = None,
    expected_market_definitions: dict[str, str] | None = None,
    kickoff_tolerance_seconds: int = 60,
    selection_protocol: Literal["latest_pre_match", "opening"] = "latest_pre_match",
) -> OddsAuditResult:
    """Validate, match, and deterministically select snapshots without post-kickoff data."""

    if kickoff_tolerance_seconds < 0:
        raise ValueError("kickoff_tolerance_seconds must not be negative")
    cutoff = _as_utc(cutoff_utc) if cutoff_utc is not None else None
    allowed = allowed_odds_types or {"opening", "pre_match"}
    match_map = {match.match_id: match for match in matches}
    accepted: list[OddsSnapshot] = []
    discarded: list[dict[str, str | None]] = []
    duplicate_keys: Counter[tuple[str, str, str, str, str, str]] = Counter()
    snapshot_selection_keys: set[tuple[str, str]] = set()

    for raw in raw_snapshots:
        snapshot_id = raw.snapshot_id if isinstance(raw, OddsSnapshot) else raw.get("snapshot_id")
        try:
            snapshot = raw if isinstance(raw, OddsSnapshot) else OddsSnapshot.model_validate(raw)
        except Exception as error:
            discarded.append(
                _discard(str(snapshot_id) if snapshot_id else None, f"schema_invalid:{error}")
            )
            continue
        match = match_map.get(snapshot.match_id)
        if match is None:
            discarded.append(_discard(snapshot.snapshot_id, "unknown_match_id"))
            continue
        captured_at = _as_utc(snapshot.captured_at)
        kickoff = _as_utc(match.kickoff_utc)
        source_kickoff = _as_utc(snapshot.match_kickoff_utc)
        if abs((source_kickoff - kickoff).total_seconds()) > kickoff_tolerance_seconds:
            discarded.append(_discard(snapshot.snapshot_id, "kickoff_mismatch"))
            continue
        if captured_at >= kickoff:
            discarded.append(_discard(snapshot.snapshot_id, "captured_at_not_before_kickoff"))
            continue
        if (
            expected_market_definitions is not None
            and expected_market_definitions.get(snapshot.market) != snapshot.market_definition
        ):
            discarded.append(_discard(snapshot.snapshot_id, "market_definition_mismatch"))
            continue
        if snapshot.odds_type not in allowed:
            discarded.append(
                _discard(
                    snapshot.snapshot_id,
                    f"odds_type_not_allowed:{snapshot.odds_type}",
                )
            )
            continue
        if cutoff is not None and captured_at >= cutoff:
            discarded.append(_discard(snapshot.snapshot_id, "captured_at_not_before_cutoff"))
            continue
        snapshot_selection_key = (snapshot.snapshot_id, snapshot.selection)
        if snapshot_selection_key in snapshot_selection_keys:
            discarded.append(_discard(snapshot.snapshot_id, "duplicate_outcome_in_snapshot"))
            continue
        snapshot_selection_keys.add(snapshot_selection_key)
        key = (
            snapshot.match_id,
            snapshot.market,
            snapshot.selection,
            snapshot.odds_type,
            captured_at.isoformat(),
            snapshot.source_name,
        )
        duplicate_keys[key] += 1
        accepted.append(snapshot)

    for key, count in duplicate_keys.items():
        if count <= 1:
            continue
        for snapshot in accepted[:]:
            snapshot_key = (
                snapshot.match_id,
                snapshot.market,
                snapshot.selection,
                snapshot.odds_type,
                _as_utc(snapshot.captured_at).isoformat(),
                snapshot.source_name,
            )
            if snapshot_key == key:
                accepted.remove(snapshot)
                discarded.append(_discard(snapshot.snapshot_id, "duplicate_snapshot_key"))

    selected: list[OddsSnapshot] = []
    groups: dict[tuple[str, str, str, str], list[OddsSnapshot]] = {}
    for snapshot in accepted:
        group_key = (snapshot.match_id, snapshot.market, snapshot.selection, snapshot.odds_type)
        groups.setdefault(group_key, []).append(snapshot)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (_as_utc(item.captured_at), item.snapshot_id))
        keep = ordered[0] if selection_protocol == "opening" else ordered[-1]
        selected.append(keep)
        discarded.extend(
            _discard(item.snapshot_id, f"superseded_by_{selection_protocol}")
            for item in ordered
            if item.snapshot_id != keep.snapshot_id
        )
    selected.sort(key=lambda item: (_as_utc(item.captured_at), item.match_id, item.snapshot_id))
    seasons = {match.match_id: match.season for match in matches}
    summary = {
        "raw_snapshots": len(raw_snapshots),
        "valid_snapshots_before_selection": len(accepted),
        "valid_snapshots": len(selected),
        "discarded_rows": len(discarded),
        "discarded_by_reason": dict(sorted(Counter(row["reason"] for row in discarded).items())),
        "coverage_by_season": dict(
            sorted(
                Counter(seasons.get(snapshot.match_id, "unknown") for snapshot in selected).items()
            )
        ),
        "coverage_by_season_market_source": {
            "|".join(key): count
            for key, count in sorted(
                Counter(
                    (
                        seasons.get(snapshot.match_id, "unknown"),
                        snapshot.market,
                        snapshot.source_name,
                    )
                    for snapshot in selected
                ).items()
            )
        },
        "first_captured_at": (
            _as_utc(selected[0].captured_at).isoformat() if selected else None
        ),
        "last_captured_at": (
            _as_utc(selected[-1].captured_at).isoformat() if selected else None
        ),
        "selection_protocol": selection_protocol,
        "allowed_odds_types": sorted(allowed),
        "kickoff_tolerance_seconds": kickoff_tolerance_seconds,
    }
    return OddsAuditResult(accepted=selected, discarded_rows=discarded, summary=summary)


def market_implied_probability(decimal_odds: float) -> float:
    """Return raw implied probability; this is not a true probability claim."""

    if decimal_odds <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    return 1.0 / decimal_odds


def remove_binary_overround_from_snapshots(
    snapshots: list[OddsSnapshot],
) -> dict[str, float]:
    """Normalize exactly two distinct selections; reject non-binary markets explicitly."""

    if len(snapshots) != 2 or snapshots[0].market != snapshots[1].market:
        raise ValueError("binary overround requires exactly two selections from one market")
    if snapshots[0].selection == snapshots[1].selection:
        raise ValueError("binary selections must be distinct")
    implied = [market_implied_probability(snapshot.decimal_odds) for snapshot in snapshots]
    total = sum(implied)
    return {
        "overround": total,
        "fair_probability_a": implied[0] / total,
        "fair_probability_b": implied[1] / total,
    }
