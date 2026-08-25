"""Grouped, descriptive-only commercial evaluation reports."""

from __future__ import annotations

from typing import Any

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary_extended
from football_prediction_lab.evaluation.odds_benchmark import (
    compare_model_to_market,
    paired_bootstrap_comparison,
)

_REQUIRED_GROUP_COLUMNS = {
    "match_id",
    "season",
    "market",
    "odds_type",
    "source",
    "model_probability",
    "market_implied_probability",
    "actual",
    "baseline_probability",
}


def _status(interval: dict[str, float] | None) -> str:
    if interval is None:
        return "unavailable"
    if interval["lower"] <= 0 <= interval["upper"]:
        return "indeterminate"
    if interval["lower"] > 0:
        return "positive_association_not_profitability"
    return "negative_association"


def assert_no_protected_holdout(
    frame: pd.DataFrame,
    *,
    season_column: str = "season",
    protected_seasons: set[str] | None = None,
) -> None:
    """Fail closed when a protected season enters historical commercial evaluation."""

    protected = protected_seasons or {"2526"}
    if season_column not in frame:
        raise ValueError(f"missing protected-season column: {season_column}")
    observed = set(frame[season_column].astype(str))
    leaked = observed.intersection(protected)
    if leaked:
        raise ValueError(f"protected holdout seasons present: {sorted(leaked)}")


def build_grouped_market_report(
    frame: pd.DataFrame,
    *,
    n_resamples: int = 1_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Build reproducible descriptive metrics without selecting odds after outcomes."""

    missing = _REQUIRED_GROUP_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing report columns: {sorted(missing)}")
    assert_no_protected_holdout(frame)
    if frame["match_id"].duplicated().any():
        raise ValueError("commercial report requires one selected market row per match")

    groups: list[dict[str, Any]] = []
    for keys, group in frame.groupby(
        ["season", "market", "odds_type", "source"], sort=True, dropna=False
    ):
        season, market, odds_type, source = (str(value) for value in keys)
        metrics = evaluate_binary_extended(
            group["model_probability"],
            group["actual"],
            baseline_probability=group["baseline_probability"],
        )
        comparison = compare_model_to_market(
            group["model_probability"],
            group["market_implied_probability"],
            group["actual"],
        )
        uncertainty = paired_bootstrap_comparison(
            group[
                [
                    "match_id",
                    "model_probability",
                    "market_implied_probability",
                    "actual",
                    "baseline_probability",
                ]
            ],
            n_resamples=n_resamples,
            seed=seed,
            confidence=confidence,
        )
        skill_status = {
            name: _status(uncertainty["intervals"][name])
            for name in ("brier_skill_score", "log_loss_skill_score")
        }
        groups.append(
            {
                "season": season,
                "market": market,
                "odds_type": odds_type,
                "source": source,
                "metrics": metrics,
                "comparison": comparison,
                "uncertainty": uncertainty,
                "skill_status": skill_status,
            }
        )
    return {
        "financial_execution": False,
        "recommendation": False,
        "roi_or_cumulative_profit": False,
        "protected_holdout_policy": "2526 rejected before grouping",
        "groups": groups,
    }
