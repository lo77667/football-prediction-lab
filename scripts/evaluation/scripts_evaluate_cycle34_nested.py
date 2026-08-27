"""Run Cycle 34 nested walk-forward selection without selection-on-outer-test."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from football_prediction_lab.data.provenance import build_manifest, sha256_file, write_manifest
from football_prediction_lab.evaluation.metrics import (
    evaluate_binary_extended,
    expected_calibration_error,
)
from football_prediction_lab.evaluation.nested_walk_forward import (
    build_nested_folds,
    paired_bootstrap_outer_test,
    select_variant_on_inner_validation,
)
from football_prediction_lab.features.cards import (
    CARD_FEATURE_COLUMNS,
    LEGACY_CARD_FEATURE_COLUMNS,
    build_card_features,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
REPORT = ROOT / "reports" / "generated" / "cycle_34_nested_walk_forward.json"
CSV_OUTPUT = ROOT / "reports" / "generated" / "cycle_34_nested_fold_metrics.csv"
PROTECTED_SEASONS = {"2526"}
BOOTSTRAP_SEED = 3401
BOOTSTRAP_REPLICATES = 400


def _metric(probability: np.ndarray, actual: np.ndarray) -> dict[str, float | None]:
    actual = actual.astype(int)
    probability = probability.astype(float)
    if len(actual) == 0:
        return {"brier_score": None, "log_loss": None, "roc_auc": None, "average_precision": None}
    clipped = np.clip(probability, 1e-15, 1 - 1e-15)
    result: dict[str, float | None] = {
        "brier_score": float(np.mean((probability - actual) ** 2)),
        "log_loss": float(-np.mean(actual * np.log(clipped) + (1 - actual) * np.log(1 - clipped))),
        "roc_auc": None,
        "average_precision": None,
    }
    if len(np.unique(actual)) == 2:
        result["roc_auc"] = float(roc_auc_score(actual, probability))
        result["average_precision"] = float(average_precision_score(actual, probability))
    return result


def _model(market: str, variant: str) -> Any:
    if market == "btts":
        columns = LEGACY_FEATURE_COLUMNS if variant == "legacy" else FEATURE_COLUMNS
        return BttsLogisticBaseline(feature_columns=columns)
    columns = LEGACY_CARD_FEATURE_COLUMNS if variant == "legacy" else CARD_FEATURE_COLUMNS
    return TotalYellowCardsBaseline(feature_columns=columns)


def _target(market: str) -> str:
    return "btts" if market == "btts" else "total_yellows_over_3_5"


def _split_calibration(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    seasons = sorted(frame["season"].astype(str).unique())
    if len(seasons) < 2:
        return None
    calibration_season = seasons[-1]
    train = frame[frame["season"].astype(str).isin(seasons[:-1])]
    calibration = frame[frame["season"].astype(str) == calibration_season]
    return train, calibration


def _predict_variant(
    market: str,
    variant: str,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[np.ndarray | None, str | None]:
    target = _target(market)
    if variant == "constant_train_rate":
        return np.full(len(evaluation), float(train[target].mean()), dtype=float), None
    if variant.startswith("platt_"):
        split = _split_calibration(train)
        if split is None:
            return None, "insufficient_inner_history_for_platt"
        fit_train, calibration = split
        base_name = "expanded" if market == "btts" else "referee_enhanced"
        model = _model(market, base_name).fit(fit_train)
        calibration_probability = model.predict_probability(calibration)
        evaluation_probability = model.predict_probability(evaluation)
        calibrated = platt_calibrate(
            calibration_probability,
            calibration[target],
            evaluation_probability,
            c_value=1.0,
        )
        return calibrated.to_numpy(dtype=float), None
    try:
        model = _model(market, variant).fit(train)
        return model.predict_probability(evaluation).to_numpy(dtype=float), None
    except (KeyError, ValueError) as exc:
        return None, str(exc)


def _evaluate(probability: np.ndarray, actual: pd.Series, baseline: np.ndarray) -> dict[str, Any]:
    actual_array = actual.to_numpy(dtype=int)
    metrics = evaluate_binary_extended(probability, actual_array, baseline_probability=baseline)
    metrics["ece_10"] = expected_calibration_error(probability, actual_array, bins=10)
    metrics["coverage"] = 1.0
    return metrics


def _bootstrap_metrics(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    match_ids: np.ndarray,
) -> dict[str, Any]:
    functions = {
        "delta_brier": lambda y, p: float(np.mean((p - y) ** 2)),
        "delta_log_loss": lambda y, p: float(
            -np.mean(
                y * np.log(np.clip(p, 1e-15, 1 - 1e-15))
                + (1 - y) * np.log(np.clip(1 - p, 1e-15, 1 - 1e-15))
            )
        ),
    }
    result: dict[str, Any] = {
        "unit": "match_id",
        "seed": BOOTSTRAP_SEED,
        "replicates": BOOTSTRAP_REPLICATES,
    }
    for name, metric_fn in functions.items():
        result[name] = paired_bootstrap_outer_test(
            actual,
            candidate,
            baseline,
            match_ids,
            metric_fn,
            seed=BOOTSTRAP_SEED,
            replicates=BOOTSTRAP_REPLICATES,
        )
    if len(np.unique(actual)) == 2:
        result["delta_roc_auc"] = paired_bootstrap_outer_test(
            actual,
            candidate,
            baseline,
            match_ids,
            lambda y, p: float(roc_auc_score(y, p)),
            seed=BOOTSTRAP_SEED,
            replicates=BOOTSTRAP_REPLICATES,
        )
        result["delta_average_precision"] = paired_bootstrap_outer_test(
            actual,
            candidate,
            baseline,
            match_ids,
            lambda y, p: float(average_precision_score(y, p)),
            seed=BOOTSTRAP_SEED,
            replicates=BOOTSTRAP_REPLICATES,
        )
    return result


def _fold_metadata(frame: pd.DataFrame, market: str) -> list[dict[str, Any]]:
    counts = frame.groupby(frame["season"].astype(str)).size().astype(int).to_dict()
    ranges = {
        str(season): (
            frame.loc[frame["season"].astype(str) == str(season), "kickoff_utc"].min().isoformat(),
            frame.loc[frame["season"].astype(str) == str(season), "kickoff_utc"].max().isoformat(),
        )
        for season in counts
    }
    feature_version = (
        "pre-match-rolling-v0.2" if market == "btts" else "card-team-referee-rolling-v0.2"
    )
    model_version = "btts-logistic-v0.2" if market == "btts" else "cards-logistic-v0.2"
    return [
        {**fold.as_dict(), "market": market}
        for fold in build_nested_folds(
            counts.keys(),
            row_counts=counts,
            prediction_ranges=ranges,
            feature_version=feature_version,
            model_version=model_version,
            protected_seasons=PROTECTED_SEASONS,
        )
    ]


def evaluate_market(
    frame: pd.DataFrame, market: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target = _target(market)
    variants = (
        ["constant_train_rate", "legacy", "expanded", "platt_expanded"]
        if market == "btts"
        else ["constant_train_rate", "legacy", "referee_enhanced", "platt_referee_enhanced"]
    )
    rows: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []
    for fold in _fold_metadata(frame, market):
        outer_train = frame[frame["season"].astype(str).isin(fold["outer_train_seasons"])]
        inner_train = frame[frame["season"].astype(str).isin(fold["inner_train_seasons"])]
        inner_validation = frame[frame["season"].astype(str).isin(fold["inner_validation_seasons"])]
        outer_test = frame[frame["season"].astype(str).isin(fold["outer_test_seasons"])]
        inner_metrics: dict[str, dict[str, float | int | None]] = {}
        candidate_status: dict[str, str | None] = {}
        for variant in variants:
            probability, reason = _predict_variant(market, variant, inner_train, inner_validation)
            if probability is None:
                candidate_status[variant] = reason
                continue
            baseline = np.full(
                len(inner_validation), float(inner_train[target].mean()), dtype=float
            )
            evaluated = _evaluate(probability, inner_validation[target], baseline)
            inner_metrics[variant] = {
                "brier_score": evaluated["brier_score"],
                "log_loss": evaluated["log_loss"],
                "ece_10": evaluated["ece_10"],
                "coverage": evaluated["coverage"],
            }
            candidate_status[variant] = None
        selection = select_variant_on_inner_validation(inner_metrics)
        selected_variant = str(selection["selected_variant"])
        outer_probability, outer_reason = _predict_variant(
            market, selected_variant, outer_train, outer_test
        )
        if outer_probability is None:
            raise RuntimeError(f"selected variant failed on outer test: {outer_reason}")
        outer_baseline = np.full(len(outer_test), float(outer_train[target].mean()), dtype=float)
        outer_metrics = _evaluate(outer_probability, outer_test[target], outer_baseline)
        actual = outer_test[target].to_numpy(dtype=int)
        bootstrap = _bootstrap_metrics(
            actual,
            outer_probability,
            outer_baseline,
            outer_test["match_id"].astype(str).to_numpy(),
        )
        fold_report = {
            **fold,
            "candidate_variants": variants,
            "candidate_status": candidate_status,
            "inner_metrics": inner_metrics,
            "selected_variant": selected_variant,
            "selection_rule_version": selection["selection_rule_version"],
            "selection_outer_test_used": False,
            "selected_for_outer_evaluation": True,
            "evaluated_out_of_sample": True,
            "outer_test_metrics": outer_metrics,
            "baseline_outer_test_metrics": _evaluate(
                outer_baseline, outer_test[target], outer_baseline
            ),
            "outer_test_bootstrap_vs_baseline": bootstrap,
            "commercial_release": False,
            "commercial_release_reason": "no_real_odds_and_future_holdout_not_released",
        }
        fold_reports.append(fold_report)
        rows.append(
            {
                "fold_id": fold["fold_id"],
                "market": market,
                "outer_test_season": fold["outer_test_seasons"][0],
                "selected_variant": selected_variant,
                "inner_brier_score": inner_metrics[selected_variant]["brier_score"],
                "inner_log_loss": inner_metrics[selected_variant]["log_loss"],
                "inner_ece_10": inner_metrics[selected_variant]["ece_10"],
                "outer_brier_score": outer_metrics["brier_score"],
                "outer_log_loss": outer_metrics["log_loss"],
                "outer_roc_auc": outer_metrics["roc_auc"],
                "outer_average_precision": outer_metrics["average_precision"],
                "outer_brier_skill_score": outer_metrics["brier_skill_score"],
                "outer_log_loss_skill_score": outer_metrics["log_loss_skill_score"],
                "selection_outer_test_used": False,
                "commercial_release": False,
            }
        )
    return rows, fold_reports


def _pooled(folds: list[dict[str, Any]]) -> dict[str, Any]:
    def mean_metric(name: str) -> float | None:
        values = [
            fold["outer_test_metrics"].get(name)
            for fold in folds
            if fold["outer_test_metrics"].get(name) is not None
        ]
        return float(np.mean(values)) if values else None

    return {
        "folds": len(folds),
        "rows": sum(int(fold["outer_test_metrics"]["rows"]) for fold in folds),
        "selected_variant_counts": pd.Series([fold["selected_variant"] for fold in folds])
        .value_counts()
        .to_dict(),
        "outer_brier_mean": mean_metric("brier_score"),
        "outer_log_loss_mean": mean_metric("log_loss"),
        "outer_roc_auc_mean": mean_metric("roc_auc"),
        "outer_average_precision_mean": mean_metric("average_precision"),
        "outer_ece_mean": mean_metric("ece_10"),
        "commercial_release": False,
    }


def _write_csv(rows: list[dict[str, Any]]) -> None:
    CSV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _manifest(path: Path, input_path: str, output_path: str, rows_after: int) -> None:
    manifest = build_manifest(
        input_path=input_path,
        input_sha256=sha256_file(ROOT / input_path),
        output_path=output_path,
        rows_before=len(pd.read_csv(ROOT / input_path)),
        rows_after=rows_after,
        frame=pd.DataFrame({"kickoff_utc": []}),
        feature_version="cycle34-nested-walk-forward-v1",
    )
    write_manifest(manifest, path)


def main() -> int:
    btts = pd.read_csv(PROCESSED / "epl_1516_2425_features.csv", parse_dates=["kickoff_utc"])
    cards_raw = pd.read_csv(PROCESSED / "epl_1516_2425.csv", parse_dates=["kickoff_utc"])
    cards = build_card_features(cards_raw).merge(
        cards_raw[["match_id", "season"]], on="match_id", how="left", validate="one_to_one"
    )
    btts = btts[~btts["season"].astype(str).isin(PROTECTED_SEASONS)].copy()
    cards = cards[~cards["season"].astype(str).isin(PROTECTED_SEASONS)].copy()
    btts_rows, btts_folds = evaluate_market(btts, "btts")
    cards_rows, cards_folds = evaluate_market(cards, "cards")
    rows = btts_rows + cards_rows
    _write_csv(rows)
    report = {
        "schema_version": "cycle34-nested-walk-forward-v1",
        "cycle": 34,
        "protocol": "nested chronological outer train / inner validation / outer test",
        "protected_seasons": sorted(PROTECTED_SEASONS),
        "selection_rule_version": "inner_brier_then_log_loss_then_ece_then_simplicity-v1",
        "bootstrap": {
            "unit": "match_id",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence": 0.95,
        },
        "commercial_release": False,
        "economic_benchmark_status": "deferred",
        "financial_execution": False,
        "markets": {
            "btts": {"folds": btts_folds, "pooled": _pooled(btts_folds)},
            "cards": {"folds": cards_folds, "pooled": _pooled(cards_folds)},
        },
        "test_summary": json.loads(
            (ROOT / "reports/generated/cycle_32_test_summary.json").read_text()
        ),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    _manifest(
        REPORT.parent / "manifests/cycle_34_nested_walk_forward.manifest.json",
        "data/processed/epl_1516_2425_features.csv",
        str(REPORT),
        len(rows),
    )
    _manifest(
        REPORT.parent / "manifests/cycle_34_nested_fold_metrics.manifest.json",
        "data/processed/epl_1516_2425_features.csv",
        str(CSV_OUTPUT),
        len(rows),
    )
    print(
        json.dumps(
            {"report": str(REPORT), "csv": str(CSV_OUTPUT), "fold_rows": len(rows)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
