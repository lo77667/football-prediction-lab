"""Selection and uncertainty helpers for Cycle 36 development evaluation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from football_prediction_lab.evaluation.metrics import (
    evaluate_binary_extended,
    expected_calibration_error,
)
from football_prediction_lab.evaluation.nested_walk_forward import (
    SELECTION_RULE_VERSION,
    build_nested_folds,
)
from football_prediction_lab.features.cards import (
    CARD_FEATURE_COLUMNS,
    LEGACY_CARD_FEATURE_COLUMNS,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline
from football_prediction_lab.models.poisson_btts import PoissonGoalsBtts
from football_prediction_lab.models.poisson_cards import PoissonCardsRate

PROTECTED_SEASONS = {"2526"}
CANDIDATES = {
    "btts": (
        "constant_train_rate",
        "logistic_legacy",
        "logistic_expanded",
        "poisson_goals_btts",
    ),
    "cards": (
        "constant_train_rate",
        "cards_logistic_legacy",
        "cards_logistic_referee_enhanced",
        "poisson_cards_rate",
    ),
}
CANDIDATE_COMPLEXITY = {
    "constant_train_rate": 0,
    "logistic_legacy": 1,
    "cards_logistic_legacy": 1,
    "logistic_expanded": 2,
    "cards_logistic_referee_enhanced": 2,
    "poisson_goals_btts": 2,
    "poisson_cards_rate": 2,
}
BOOTSTRAP_SEED = 3601
BOOTSTRAP_REPLICATES = 1_000


def target_for_market(market: str) -> str:
    return "btts" if market == "btts" else "total_yellows_over_3_5"


def candidate_names(market: str) -> tuple[str, ...]:
    try:
        return CANDIDATES[market]
    except KeyError as exc:
        raise ValueError(f"unknown market: {market}") from exc


def _model(market: str, candidate: str) -> Any:
    if market == "btts":
        if candidate == "logistic_legacy":
            return BttsLogisticBaseline(feature_columns=LEGACY_FEATURE_COLUMNS)
        if candidate == "logistic_expanded":
            return BttsLogisticBaseline(feature_columns=FEATURE_COLUMNS)
        if candidate == "poisson_goals_btts":
            return PoissonGoalsBtts()
    else:
        if candidate == "cards_logistic_legacy":
            return TotalYellowCardsBaseline(feature_columns=LEGACY_CARD_FEATURE_COLUMNS)
        if candidate == "cards_logistic_referee_enhanced":
            return TotalYellowCardsBaseline(feature_columns=CARD_FEATURE_COLUMNS)
        if candidate == "poisson_cards_rate":
            return PoissonCardsRate()
    raise ValueError(f"unsupported model candidate {candidate} for {market}")


def predict_candidate(
    market: str,
    candidate: str,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[np.ndarray | None, str | None]:
    target = target_for_market(market)
    if candidate == "constant_train_rate":
        if target not in train or train[target].empty:
            return None, "missing_training_target"
        return np.full(len(evaluation), float(train[target].mean()), dtype=float), None
    try:
        model = _model(market, candidate).fit(train)
        return model.predict_probability(evaluation).to_numpy(dtype=float), None
    except (KeyError, ValueError, RuntimeError) as exc:
        return None, str(exc)


def score_probability(
    probability: np.ndarray,
    actual: np.ndarray,
    baseline: np.ndarray,
    *,
    threshold: float = 0.5,
) -> dict[str, float | int | None]:
    result = evaluate_binary_extended(
        probability,
        actual,
        baseline_probability=baseline,
        threshold=threshold,
    )
    result["ece_10"] = expected_calibration_error(probability, actual, bins=10)
    return result


def select_inner_candidate(inner_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Select by inner metrics only: Brier, Log Loss, ECE, then simplicity."""

    if not inner_metrics:
        raise ValueError("no available candidates for inner selection")
    required = ("brier_score", "log_loss", "ece_10")
    for candidate, metrics in inner_metrics.items():
        if any(metrics.get(name) is None for name in required):
            raise ValueError(f"incomplete inner metrics for {candidate}")
    selected = min(
        inner_metrics,
        key=lambda name: (
            float(inner_metrics[name]["brier_score"]),
            float(inner_metrics[name]["log_loss"]),
            float(inner_metrics[name]["ece_10"]),
            CANDIDATE_COMPLEXITY.get(name, 99),
            name,
        ),
    )
    return {
        "selected_variant": selected,
        "selection_rule_version": SELECTION_RULE_VERSION,
        "selection_basis": {name: inner_metrics[selected][name] for name in required},
        "outer_test_used": False,
        "selection_used_2526": False,
        "simplicity_order": CANDIDATE_COMPLEXITY,
    }


def market_folds(frame: pd.DataFrame, market: str) -> list[dict[str, Any]]:
    frame = frame.copy()
    frame["season"] = frame["season"].astype(str)
    seasons = sorted(frame["season"].unique())
    if PROTECTED_SEASONS.intersection(seasons):
        raise ValueError("2526 cannot enter Cycle 36 development folds")
    counts = frame.groupby("season").size().astype(int).to_dict()
    ranges = {
        season: (
            frame.loc[frame["season"] == season, "kickoff_utc"].min().isoformat(),
            frame.loc[frame["season"] == season, "kickoff_utc"].max().isoformat(),
        )
        for season in seasons
    }
    feature_version = (
        "pre-match-cycle36-btts-v1" if market == "btts" else "pre-match-cycle36-cards-v1"
    )
    model_version = "cycle36-candidate-suite-v1"
    return [
        {**fold.as_dict(), "market": market}
        for fold in build_nested_folds(
            seasons,
            row_counts=counts,
            prediction_ranges=ranges,
            feature_version=feature_version,
            model_version=model_version,
            protected_seasons=PROTECTED_SEASONS,
        )
    ]


def _safe_metric(
    function: Callable[[np.ndarray, np.ndarray], float],
    actual: np.ndarray,
    probability: np.ndarray,
) -> float | None:
    if len(np.unique(actual)) < 2:
        return None
    return float(function(actual, probability))


def paired_bootstrap(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    match_ids: np.ndarray,
    *,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Return deterministic paired intervals, grouped by match_id."""

    unique, inverse = np.unique(match_ids.astype(str), return_inverse=True)
    if len(unique) == 0:
        return {"status": "inconclusive", "reason": "no_rows", "unit": "match_id"}
    functions: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
        "delta_brier": lambda y, p: float(np.mean((p - y) ** 2)),
        "delta_log_loss": lambda y, p: float(
            -np.mean(
                y * np.log(np.clip(p, 1e-15, 1 - 1e-15))
                + (1 - y) * np.log(np.clip(1 - p, 1e-15, 1 - 1e-15))
            )
        ),
        "delta_roc_auc": lambda y, p: float(roc_auc_score(y, p)),
        "delta_average_precision": lambda y, p: float(average_precision_score(y, p)),
    }
    rng = np.random.default_rng(seed)
    output: dict[str, Any] = {
        "status": "ok",
        "unit": "match_id",
        "seed": seed,
        "replicates": replicates,
    }
    for name, function in functions.items():
        values: list[float] = []
        for _ in range(replicates):
            sampled = rng.integers(0, len(unique), size=len(unique))
            indices = np.concatenate([np.flatnonzero(inverse == group) for group in sampled])
            candidate_value = _safe_metric(function, actual[indices], candidate[indices])
            baseline_value = _safe_metric(function, actual[indices], baseline[indices])
            if candidate_value is not None and baseline_value is not None:
                values.append(candidate_value - baseline_value)
        if not values:
            output[name] = {
                "status": "inconclusive",
                "reason": "bootstrap_samples_lacked_two_classes",
            }
            continue
        low, high = np.quantile(values, [0.025, 0.975])
        output[name] = {
            "status": "ok",
            "delta_mean": float(np.mean(values)),
            "lower_95": float(low),
            "upper_95": float(high),
            "interval_status": "inconclusive" if low <= 0 <= high else "directional",
        }
    return output


def summarize_stability(folds: list[dict[str, Any]]) -> dict[str, Any]:
    if not folds:
        return {"status": "inconclusive", "reason": "no_folds"}
    selected = [fold["selected_variant"] for fold in folds]
    counts = pd.Series(selected).value_counts().to_dict()
    wins = [
        fold["outer_test_metrics"]["brier_score"]
        < fold["baseline_outer_test_metrics"]["brier_score"]
        for fold in folds
    ]
    deltas = [
        fold["outer_test_metrics"]["brier_score"]
        - fold["baseline_outer_test_metrics"]["brier_score"]
        for fold in folds
    ]
    share_wins = float(np.mean(wins))
    max_abs_delta = float(max(abs(value) for value in deltas))
    if share_wins >= 0.75 and max_abs_delta <= 0.05:
        status = "stable"
    elif share_wins <= 0.25 or max_abs_delta > 0.15:
        status = "unstable"
    else:
        status = "inconclusive"
    return {
        "status": status,
        "thresholds_declared_before_run": {
            "stable_brier_win_share_min": 0.75,
            "stable_max_abs_brier_delta_max": 0.05,
            "unstable_brier_win_share_max": 0.25,
            "unstable_max_abs_brier_delta_gt": 0.15,
        },
        "selection_counts": counts,
        "brier_win_share_vs_baseline": share_wins,
        "mean_brier_delta_per_fold": float(np.mean(deltas)),
        "weighted_brier_delta": float(
            sum(
                fold["outer_test_metrics"]["brier_score"] * fold["outer_test_metrics"]["rows"]
                for fold in folds
            )
            / sum(fold["outer_test_metrics"]["rows"] for fold in folds)
            - sum(
                fold["baseline_outer_test_metrics"]["brier_score"]
                * fold["outer_test_metrics"]["rows"]
                for fold in folds
            )
            / sum(fold["outer_test_metrics"]["rows"] for fold in folds)
        ),
        "worst_fold": max(
            folds,
            key=lambda fold: (
                fold["outer_test_metrics"]["brier_score"]
                - fold["baseline_outer_test_metrics"]["brier_score"]
            ),
        )["fold_id"],
        "largest_seasonal_brier_change": float(
            max(
                (
                    abs(
                        a["outer_test_metrics"]["brier_score"]
                        - b["outer_test_metrics"]["brier_score"]
                    )
                    for a, b in zip(folds, folds[1:], strict=False)
                ),
                default=0.0,
            )
        ),
        "folds": len(folds),
    }
