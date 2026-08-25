"""Nested chronological model selection for Cycle 34."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class NestedFold:
    fold_id: str
    outer_train_seasons: tuple[str, ...]
    inner_train_seasons: tuple[str, ...]
    inner_validation_seasons: tuple[str, ...]
    outer_test_seasons: tuple[str, ...]
    outer_training_cutoff: str
    inner_validation_start: str
    inner_validation_end: str
    outer_test_start: str
    outer_test_end: str
    train_rows: int
    inner_train_rows: int
    inner_validation_rows: int
    outer_test_rows: int
    feature_version: str
    model_version: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_nested_folds(
    seasons: Iterable[str],
    *,
    row_counts: dict[str, int],
    prediction_ranges: dict[str, tuple[str, str]],
    feature_version: str,
    model_version: str,
    protected_seasons: set[str] | None = None,
) -> list[NestedFold]:
    """Build expanding outer folds with the last outer-train season as inner validation."""

    protected = protected_seasons or {"2526"}
    ordered = tuple(sorted({str(season) for season in seasons}))
    if any(season in protected for season in ordered):
        raise ValueError("protected seasons cannot appear in nested folds")
    if len(ordered) < 3:
        raise ValueError("at least three seasons are required for nested folds")
    folds: list[NestedFold] = []
    for index in range(2, len(ordered)):
        outer_train = ordered[:index]
        inner_train = ordered[: index - 1]
        inner_validation = (ordered[index - 1],)
        outer_test = (ordered[index],)
        if not max(inner_train) < min(inner_validation) < min(outer_test):
            raise ValueError("nested partitions must be strictly chronological")
        partitions = (inner_train, inner_validation, outer_test)
        flattened = [season for partition in partitions for season in partition]
        if len(flattened) != len(set(flattened)):
            raise ValueError("nested partitions must not overlap")
        if any(season in protected for season in flattened):
            raise ValueError("protected season entered nested fold")
        if any(season not in row_counts for season in flattened):
            raise ValueError("nested fold row metadata is incomplete")
        if any(season not in prediction_ranges for season in inner_validation + outer_test):
            raise ValueError("nested fold prediction metadata is incomplete")
        validation_start, validation_end = prediction_ranges[inner_validation[0]]
        test_start, test_end = prediction_ranges[outer_test[0]]
        folds.append(
            NestedFold(
                fold_id=f"fold_{len(folds) + 1:02d}",
                outer_train_seasons=outer_train,
                inner_train_seasons=inner_train,
                inner_validation_seasons=inner_validation,
                outer_test_seasons=outer_test,
                outer_training_cutoff=f"{max(outer_train)}-12-31T23:59:59Z",
                inner_validation_start=validation_start,
                inner_validation_end=validation_end,
                outer_test_start=test_start,
                outer_test_end=test_end,
                train_rows=sum(row_counts[season] for season in outer_train),
                inner_train_rows=sum(row_counts[season] for season in inner_train),
                inner_validation_rows=sum(row_counts[season] for season in inner_validation),
                outer_test_rows=sum(row_counts[season] for season in outer_test),
                feature_version=feature_version,
                model_version=model_version,
            )
        )
    return folds


SELECTION_RULE_VERSION = "inner_brier_then_log_loss_then_ece_then_simplicity-v1"
SIMPLE_VARIANT_ORDER = {
    "constant_train_rate": 0,
    "legacy": 1,
    "expanded": 2,
    "referee_enhanced": 2,
    "platt_expanded": 3,
    "platt_referee_enhanced": 3,
}


def select_variant_on_inner_validation(
    inner_metrics: dict[str, dict[str, float | int | None]],
    *,
    brier_tolerance: float = 1e-12,
    log_loss_tolerance: float = 1e-12,
    ece_tolerance: float = 1e-12,
) -> dict[str, Any]:
    """Select using inner metrics only; no outer-test argument exists by design."""

    if not inner_metrics:
        raise ValueError("inner_metrics must not be empty")
    candidates = list(inner_metrics)
    missing = [
        name
        for name, metrics in inner_metrics.items()
        if any(metrics.get(key) is None for key in ("brier_score", "log_loss", "ece_10"))
    ]
    if missing:
        raise ValueError(f"inner metrics incomplete for: {missing}")

    def key(name: str) -> tuple[float, float, float, int, str]:
        metrics = inner_metrics[name]
        return (
            float(metrics["brier_score"]),
            float(metrics["log_loss"]),
            float(metrics["ece_10"]),
            SIMPLE_VARIANT_ORDER.get(name, 99),
            name,
        )

    ordered = sorted(candidates, key=key)
    selected = ordered[0]
    return {
        "selected_variant": selected,
        "candidate_variants": candidates,
        "selection_rule_version": SELECTION_RULE_VERSION,
        "selection_basis": {
            "brier_score": inner_metrics[selected]["brier_score"],
            "log_loss": inner_metrics[selected]["log_loss"],
            "ece_10": inner_metrics[selected]["ece_10"],
        },
        "inner_metrics": inner_metrics,
        "outer_test_used": False,
        "tolerances": {
            "brier": brier_tolerance,
            "log_loss": log_loss_tolerance,
            "ece": ece_tolerance,
        },
    }


def paired_bootstrap_outer_test(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    match_ids: np.ndarray,
    metric_fn: Any,
    *,
    seed: int = 3401,
    replicates: int = 400,
) -> dict[str, Any]:
    """Describe selected-vs-baseline uncertainty on outer test, grouped by match_id."""

    if not (len(actual) == len(candidate) == len(baseline) == len(match_ids)):
        raise ValueError("bootstrap inputs must have equal lengths")
    unique, inverse = np.unique(match_ids.astype(str), return_inverse=True)
    if len(unique) == 0:
        return {"status": "inconclusive", "reason": "no_outer_test_rows", "unit": "match_id"}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(replicates):
        sampled_groups = rng.integers(0, len(unique), size=len(unique))
        indices = np.concatenate([np.flatnonzero(inverse == group) for group in sampled_groups])
        values.append(
            float(
                metric_fn(actual[indices], candidate[indices])
                - metric_fn(actual[indices], baseline[indices])
            )
        )
    low, high = np.quantile(values, [0.025, 0.975])
    return {
        "status": "ok",
        "unit": "match_id",
        "seed": seed,
        "replicates": replicates,
        "delta_mean": float(np.mean(values)),
        "lower_95": float(low),
        "upper_95": float(high),
        "interval_status": "inconclusive" if low <= 0 <= high else "directional",
    }
