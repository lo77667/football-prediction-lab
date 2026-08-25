"""Frozen deployment policy and holdout-evaluation guards for Cycle 35."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

POLICY_SCHEMA_VERSION = "cycle35-policy-lock-v1"
PROTECTED_HOLDOUT = ("2526",)
TIE_BREAK_ORDER = (
    "constant_train_rate",
    "legacy",
    "expanded",
    "referee_enhanced",
    "platt_expanded",
    "platt_referee_enhanced",
)


@dataclass(frozen=True)
class PolicyLock:
    policy_version: str
    lock_created_at_utc: str
    source_cycle: int
    market: str
    selected_variant: str
    feature_version: str
    model_version: str
    calibration_policy: str
    training_seasons: tuple[str, ...]
    calibration_seasons: tuple[str, ...]
    training_cutoff: str
    threshold: float
    selection_rule: str
    input_artifact_hashes: dict[str, str]
    protected_holdout: tuple[str, ...] = PROTECTED_HOLDOUT
    commercial_release: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"schema_version": POLICY_SCHEMA_VERSION}


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_selection_history_excludes_holdout(
    seasons: tuple[str, ...] | list[str] | set[str],
) -> None:
    """Reject protected holdout seasons in policy selection or tuning inputs."""

    if PROTECTED_HOLDOUT[0] in {str(season) for season in seasons}:
        raise ValueError("2526 is protected and cannot enter selection or tuning")


def choose_modal_variant(counts: dict[str, int]) -> dict[str, Any]:
    if not counts:
        raise ValueError("variant counts must not be empty")
    max_count = max(counts.values())
    tied = [variant for variant, count in counts.items() if count == max_count]
    selected = min(
        tied,
        key=lambda variant: (
            TIE_BREAK_ORDER.index(variant) if variant in TIE_BREAK_ORDER else 99,
            variant,
        ),
    )
    return {
        "selected_variant": selected,
        "max_count": max_count,
        "tied_variants": sorted(tied),
        "tie_break_order": list(TIE_BREAK_ORDER),
        "rule": "modal_cycle34_variant_then_fixed_simplicity_tiebreak",
    }


def validate_policy_lock(lock: dict[str, Any]) -> None:
    if lock.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported policy lock schema")
    if tuple(lock.get("protected_holdout", ())) != PROTECTED_HOLDOUT:
        raise ValueError("policy lock must protect 2526")
    if lock.get("commercial_release") is not False:
        raise ValueError("commercial release must remain false")
    markets = lock.get("markets")
    if not isinstance(markets, dict) or not markets:
        raise ValueError("markets are required")
    if any(not details.get("selected_variant") for details in markets.values()):
        raise ValueError("selected variant is required for every market")
    if not lock.get("input_artifact_hashes"):
        raise ValueError("input artifact hashes are required")
    if not lock.get("lock_created_at_utc"):
        raise ValueError("lock timestamp is required")


def load_policy_lock(path: Path) -> dict[str, Any]:
    import json

    lock = json.loads(path.read_text(encoding="utf-8"))
    validate_policy_lock(lock)
    return lock


def assert_prediction_artifact_safe(path: Path, *, expected_policy_version: str) -> None:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("policy_version") != expected_policy_version:
        raise ValueError("prediction artifact policy version mismatch")
    if "target" in payload or "btts" in payload or "total_yellows_over_3_5" in payload:
        raise ValueError("prediction artifact must not contain targets")
    predictions = payload.get("predictions", [])
    seen_by_market: dict[str, set[str]] = {}
    for item in predictions:
        market = str(item.get("market"))
        match_id = str(item.get("match_id"))
        seen_by_market.setdefault(market, set())
        if match_id in seen_by_market[market]:
            raise ValueError("prediction artifact contains duplicate match_id within market")
        seen_by_market[market].add(match_id)
    for item in predictions:
        if item.get("issued_at") >= item.get("kickoff_utc"):
            raise ValueError("prediction issued_at must precede kickoff_utc")
        if item.get("training_cutoff") >= item.get("kickoff_utc"):
            raise ValueError("training_cutoff must precede kickoff_utc")
