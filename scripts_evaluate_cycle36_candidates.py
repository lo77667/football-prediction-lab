"""Evaluate a deliberately small, leakage-safe Cycle 36 candidate suite."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from football_prediction_lab.data.provenance import sha256_file  # noqa: E402
from football_prediction_lab.evaluation.cycle36_model_selection import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    CANDIDATE_COMPLEXITY,
    PROTECTED_SEASONS,
    candidate_names,
    market_folds,
    paired_bootstrap,
    predict_candidate,
    score_probability,
    select_inner_candidate,
    summarize_stability,
    target_for_market,
)
from football_prediction_lab.features.cards import build_card_features  # noqa: E402

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
POLICY_PATH = ROOT / "configs" / "cycle36_future_holdout_policy.json"
REPORT_PATH = ROOT / "reports" / "generated" / "cycle_36_candidate_evaluation.json"
CSV_PATH = ROOT / "reports" / "generated" / "cycle_36_fold_metrics.csv"
MANIFEST_DIR = ROOT / "reports" / "generated" / "manifests"
EXPOSED_SEASON = "2526"
FUTURE_HOLDOUT = "2627"
DEVELOPMENT_SEASONS = (
    "1516",
    "1617",
    "1718",
    "1819",
    "1920",
    "2021",
    "2122",
    "2223",
    "2324",
    "2425",
)


def _load_frames(market: str) -> tuple[pd.DataFrame, Path]:
    if market == "btts":
        path = PROCESSED / "epl_1516_2425_features.csv"
        frame = pd.read_csv(path, parse_dates=["kickoff_utc"])
    elif market == "cards":
        path = PROCESSED / "epl_1516_2425.csv"
        raw = pd.read_csv(path, parse_dates=["kickoff_utc"])
        frame = build_card_features(raw).merge(
            raw[["match_id", "season"]],
            on="match_id",
            how="left",
            validate="one_to_one",
        )
    else:
        raise ValueError(f"unknown market {market}")
    frame["kickoff_utc"] = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="raise")
    frame["season"] = frame["season"].astype(str)
    if PROTECTED_SEASONS.intersection(frame["season"].unique()):
        raise ValueError("2526 is prohibited from Cycle 36 development input")
    if set(frame["season"].unique()) != set(DEVELOPMENT_SEASONS):
        raise ValueError("development seasons do not match the Cycle 36 dataset policy")
    if frame["match_id"].duplicated().any():
        raise ValueError(f"duplicate match_id values in {market} development frame")
    return frame.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True), path


def _modal_policy_variant(selected: list[str]) -> tuple[str, dict[str, int], list[str]]:
    counts = Counter(selected)
    maximum = max(counts.values())
    tied = sorted(name for name, count in counts.items() if count == maximum)
    chosen = min(tied, key=lambda name: (CANDIDATE_COMPLEXITY.get(name, 99), name))
    return chosen, dict(sorted(counts.items())), tied


def _evaluate_market(
    frame: pd.DataFrame, market: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target = target_for_market(market)
    folds = market_folds(frame, market)
    fold_reports: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    for fold in folds:
        outer_train = frame[frame["season"].isin(fold["outer_train_seasons"])]
        inner_train = frame[frame["season"].isin(fold["inner_train_seasons"])]
        inner_validation = frame[frame["season"].isin(fold["inner_validation_seasons"])]
        outer_test = frame[frame["season"].isin(fold["outer_test_seasons"])]
        inner_metrics: dict[str, dict[str, Any]] = {}
        candidate_status: dict[str, dict[str, Any]] = {}
        for candidate in candidate_names(market):
            probability, reason = predict_candidate(
                market, candidate, inner_train, inner_validation
            )
            if probability is None:
                candidate_status[candidate] = {
                    "status": "unavailable",
                    "unavailable_reason": reason,
                }
                continue
            baseline = np.full(len(inner_validation), float(inner_train[target].mean()))
            metrics = score_probability(
                probability,
                inner_validation[target].to_numpy(dtype=int),
                baseline,
            )
            inner_metrics[candidate] = metrics
            candidate_status[candidate] = {"status": "available", "unavailable_reason": None}
        selection = select_inner_candidate(inner_metrics)
        selected = selection["selected_variant"]
        outer_probability, reason = predict_candidate(market, selected, outer_train, outer_test)
        if outer_probability is None:
            raise RuntimeError(f"selected candidate unavailable on outer test: {reason}")
        outer_actual = outer_test[target].to_numpy(dtype=int)
        outer_baseline = np.full(len(outer_test), float(outer_train[target].mean()))
        outer_metrics = score_probability(outer_probability, outer_actual, outer_baseline)
        baseline_metrics = score_probability(outer_baseline, outer_actual, outer_baseline)
        bootstrap = paired_bootstrap(
            outer_actual,
            outer_probability,
            outer_baseline,
            outer_test["match_id"].astype(str).to_numpy(),
        )
        fold_report = {
            **fold,
            "candidate_variants": list(candidate_names(market)),
            "candidate_status": candidate_status,
            "inner_metrics": inner_metrics,
            "selected_variant": selected,
            "selection_rule_version": selection["selection_rule_version"],
            "selection_basis": selection["selection_basis"],
            "selection_used_2526": False,
            "outer_test_used_for_selection": False,
            "outer_test_metrics": outer_metrics,
            "baseline_outer_test_metrics": baseline_metrics,
            "outer_bootstrap_vs_baseline": bootstrap,
            "evaluated_out_of_sample": True,
        }
        fold_reports.append(fold_report)
        csv_rows.append(
            {
                "market": market,
                "fold_id": fold["fold_id"],
                "outer_test_season": fold["outer_test_seasons"][0],
                "selected_variant": selected,
                "outer_rows": outer_metrics["rows"],
                "outer_brier_score": outer_metrics["brier_score"],
                "outer_log_loss": outer_metrics["log_loss"],
                "outer_roc_auc": outer_metrics["roc_auc"],
                "outer_average_precision": outer_metrics["average_precision"],
                "outer_ece_10": outer_metrics["ece_10"],
                "baseline_brier_score": baseline_metrics["brier_score"],
                "baseline_log_loss": baseline_metrics["log_loss"],
                "brier_delta": outer_metrics["brier_score"] - baseline_metrics["brier_score"],
                "log_loss_delta": outer_metrics["log_loss"] - baseline_metrics["log_loss"],
                "selection_used_2526": False,
            }
        )
    all_actual: list[np.ndarray] = []
    all_probability: list[np.ndarray] = []
    all_baseline: list[np.ndarray] = []
    for fold in fold_reports:
        outer_test = frame[frame["season"].isin(fold["outer_test_seasons"])]
        outer_train = frame[frame["season"].isin(fold["outer_train_seasons"])]
        probability, reason = predict_candidate(
            market,
            fold["selected_variant"],
            outer_train,
            outer_test,
        )
        if probability is None:
            raise RuntimeError(f"pooled selected candidate unavailable: {reason}")
        all_actual.append(outer_test[target].to_numpy(dtype=int))
        all_probability.append(probability)
        all_baseline.append(np.full(len(outer_test), float(outer_train[target].mean())))
    actual = np.concatenate(all_actual)
    probability = np.concatenate(all_probability)
    baseline = np.concatenate(all_baseline)
    pooled = score_probability(probability, actual, baseline)
    selected_variant, selected_counts, tied_variants = _modal_policy_variant(
        [fold["selected_variant"] for fold in fold_reports]
    )
    market_report = {
        "candidate_variants": list(candidate_names(market)),
        "folds": fold_reports,
        "pooled_selected_outer_aggregate": pooled,
        "pooled_rows": len(actual),
        "modal_deployment_candidate": selected_variant,
        "modal_selection_counts": selected_counts,
        "modal_tied_variants": tied_variants,
        "stability": summarize_stability(fold_reports),
        "selection_used_2526": False,
        "outer_test_used_for_selection": False,
        "bootstrap_scope": "per_outer_fold; paired by match_id",
    }
    return market_report, csv_rows


def _manifest(path: Path, output: Path, inputs: dict[str, Path], rows: int) -> None:
    payload = {
        "schema_version": "cycle36-manifest-v1",
        "output_path": str(output.relative_to(ROOT)),
        "output_sha256": sha256_file(output),
        "rows_after": rows,
        "timezone": "UTC",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            name: {
                "path": str(value.relative_to(ROOT)),
                "sha256": sha256_file(value),
            }
            for name, value in inputs.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    market_frames = {market: _load_frames(market) for market in ("btts", "cards")}
    market_reports: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    for market, (frame, _) in market_frames.items():
        report, rows = _evaluate_market(frame, market)
        market_reports[market] = report
        csv_rows.extend(rows)
    source_hashes = {market: sha256_file(path) for market, (_, path) in market_frames.items()}
    policy = {
        "schema_version": "cycle36-future-holdout-policy-v1",
        "policy_version": "cycle36-future-2627-policy-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "development_seasons": list(DEVELOPMENT_SEASONS),
        "exposed_seasons": [EXPOSED_SEASON],
        "future_holdout": [FUTURE_HOLDOUT],
        "future_holdout_status": "reserved_not_available_and_not_evaluated",
        "markets": {
            market: {
                "selected_candidate_policy": report["modal_deployment_candidate"],
                "candidate_selection_counts": report["modal_selection_counts"],
                "feature_version": "pre-match-cycle36-btts-v1"
                if market == "btts"
                else "pre-match-cycle36-cards-v1",
                "model_version": "cycle36-candidate-suite-v1",
                "calibration_policy": "none_selected_in_this_cycle",
                "threshold": 0.5,
            }
            for market, report in market_reports.items()
        },
        "selection_rule": {
            "version": "inner_brier_then_log_loss_then_ece_then_simplicity-v1",
            "scope": "inner_validation_only",
            "outer_test_used": False,
            "selection_used_2526": False,
            "deployment_aggregation": "modal_selected_candidate_then_fixed_complexity_tiebreak",
        },
        "artifact_hashes": {
            "input_btts": source_hashes["btts"],
            "input_cards": source_hashes["cards"],
        },
        "commercial_release": False,
        "economic_benchmark_status": "deferred",
        "financial_execution": False,
    }
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    report = {
        "schema_version": "cycle36-candidate-evaluation-v1",
        "cycle": 36,
        "development_seasons": list(DEVELOPMENT_SEASONS),
        "exposed_seasons": [EXPOSED_SEASON],
        "future_holdout": [FUTURE_HOLDOUT],
        "candidate_scope": "small_interpretable_suite_no_hyperparameter_grid",
        "candidate_definitions": {
            "constant_train_rate": "historical target rate from training partition",
            "logistic_legacy": "existing logistic baseline with legacy pre-match features",
            "logistic_expanded": "existing logistic baseline with expanded pre-match features",
            "cards_logistic_legacy": "existing cards logistic baseline with legacy features",
            "cards_logistic_referee_enhanced": (
                "existing cards logistic baseline with referee state"
            ),
            "poisson_goals_btts": (
                "independent goal-rate model with "
                "P(BTTS)=1-exp(-lambda_h)-exp(-lambda_a)+exp(-(lambda_h+lambda_a))"
            ),
            "poisson_cards_rate": (
                "Poisson total-card rate and "
                "P(total_yellows>3.5)=1-PoissonCDF(3)"
            ),
        },
        "markets": market_reports,
        "policy_lock": policy,
        "states": {
            "candidate_selected_in_inner": True,
            "evaluated_on_development_outer_test": True,
            "ready_for_future_2627_holdout": all(
                len(report["folds"]) >= 3 and report["stability"]["status"] != "unstable"
                for report in market_reports.values()
            ),
            "commercial_release": False,
        },
        "guards": {
            "2526_in_development": False,
            "2526_in_selection": False,
            "2526_in_tuning": False,
            "2526_in_calibration": False,
            "2627_evaluated": False,
            "odds_used": False,
            "roi_ev_stake_sizing_used": False,
            "current_match_post_match_features_used": False,
            "selection_used_2526": False,
        },
        "bootstrap": {
            "unit": "match_id",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence": 0.95,
            "scope": "selected candidate versus fold baseline; descriptive only",
        },
        "commercial_release": False,
        "economic_benchmark_status": "deferred",
        "financial_execution": False,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _manifest(
        MANIFEST_DIR / "cycle_36_candidate_evaluation.manifest.json",
        REPORT_PATH,
        {"btts_source": market_frames["btts"][1], "cards_source": market_frames["cards"][1]},
        sum(len(report["folds"]) for report in market_reports.values()),
    )
    _manifest(
        MANIFEST_DIR / "cycle_36_fold_metrics.manifest.json",
        CSV_PATH,
        {"evaluation": REPORT_PATH},
        len(csv_rows),
    )
    _manifest(
        MANIFEST_DIR / "cycle36_future_holdout_policy.manifest.json",
        POLICY_PATH,
        {"evaluation": REPORT_PATH},
        2,
    )
    print(
        json.dumps(
            {
                "report": str(REPORT_PATH),
                "policy": str(POLICY_PATH),
                "fold_rows": len(csv_rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
