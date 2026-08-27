"""Run Cycle 33 walk-forward model comparison for BTTS and cards."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
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
from football_prediction_lab.evaluation.walk_forward_protocol import build_season_folds
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
REPORT = ROOT / "reports" / "generated" / "cycle_33_walk_forward.json"
CSV_OUTPUT = ROOT / "reports" / "generated" / "cycle_33_fold_metrics.csv"
MIN_VALID_FOLDS = 3
ECE_TOLERANCE = 0.02
BOOTSTRAP_REPLICATES = 400
BOOTSTRAP_SEED = 3301
PROTECTED_SEASONS = {"2526"}


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    return value


def _metric_vector(probability: np.ndarray, actual: np.ndarray) -> dict[str, float | None]:
    if len(probability) == 0:
        return {"brier": None, "log_loss": None, "roc_auc": None, "average_precision": None}
    clipped = np.clip(probability.astype(float), 1e-15, 1 - 1e-15)
    brier = float(np.mean((probability - actual) ** 2))
    logloss = float(-np.mean(actual * np.log(clipped) + (1 - actual) * np.log(1 - clipped)))
    if len(np.unique(actual)) < 2:
        return {"brier": brier, "log_loss": logloss, "roc_auc": None, "average_precision": None}
    return {
        "brier": brier,
        "log_loss": logloss,
        "roc_auc": float(roc_auc_score(actual, probability)),
        "average_precision": float(average_precision_score(actual, probability)),
    }


def _paired_bootstrap(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    groups: np.ndarray,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    if not (len(actual) == len(candidate) == len(baseline) == len(groups)):
        raise ValueError("bootstrap arrays must have equal lengths")
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    n = len(unique_groups)
    if n == 0:
        return {"status": "inconclusive", "reason": "no_rows", "replicates": 0, "unit": "match_id"}
    differences: dict[str, list[float]] = {
        key: [] for key in ("brier", "log_loss", "roc_auc", "average_precision")
    }
    for _ in range(replicates):
        sampled_groups = rng.integers(0, n, size=n)
        sample = np.concatenate([np.flatnonzero(inverse == group) for group in sampled_groups])
        candidate_metrics = _metric_vector(candidate[sample], actual[sample])
        baseline_metrics = _metric_vector(baseline[sample], actual[sample])
        for key in differences:
            left = candidate_metrics[key]
            right = baseline_metrics[key]
            if left is not None and right is not None:
                differences[key].append(float(left - right))
    result: dict[str, Any] = {
        "status": "ok",
        "seed": seed,
        "replicates": replicates,
        "unit": "match_id",
    }
    for key, values in differences.items():
        if not values:
            result[key] = None
            continue
        low, high = np.quantile(values, [0.025, 0.975])
        result[key] = {
            "delta_mean": float(np.mean(values)),
            "lower_95": float(low),
            "upper_95": float(high),
            "status": "inconclusive" if low <= 0 <= high else "directional",
        }
    return result


def _model_probability(
    model_factory: Callable[[], Any],
    train: pd.DataFrame,
    test: pd.DataFrame,
    target: str,
    feature_columns: list[str],
) -> tuple[np.ndarray | None, str | None]:
    try:
        model = model_factory()
        model.fit(train)
        return model.predict_probability(test).to_numpy(dtype=float), None
    except (ValueError, KeyError) as exc:
        return None, str(exc)


def _ranking_diagnostic(probability: np.ndarray, actual: np.ndarray) -> dict[str, Any]:
    if len(actual) < 100:
        return {"top_decile_precision": None, "reason": "insufficient_rows_for_decile"}
    order = np.argsort(-probability, kind="stable")
    top_count = max(1, int(np.ceil(len(actual) / 10)))
    return {
        "top_decile_precision": float(np.mean(actual[order[:top_count]])),
        "top_decile_rows": top_count,
        "reason": None,
    }


def _evaluate_predictions(
    probability: np.ndarray,
    actual: pd.Series,
    baseline_probability: np.ndarray,
    *,
    expected_rows: int,
) -> dict[str, Any]:
    actual_array = actual.to_numpy(dtype=int)
    evaluated = evaluate_binary_extended(
        probability,
        actual_array,
        baseline_probability=baseline_probability,
        expected_rows=expected_rows,
    )
    evaluated["ece_10"] = expected_calibration_error(probability, actual_array, bins=10)
    evaluated["mean_probability"] = float(np.mean(probability))
    evaluated["actual_rate"] = float(np.mean(actual_array))
    evaluated["ranking_diagnostic"] = _ranking_diagnostic(probability, actual_array)
    return {key: _json_value(value) for key, value in evaluated.items()}


def _fold_rows(
    frame: pd.DataFrame,
    fold: dict[str, Any],
    *,
    target: str,
    variants: dict[str, Callable[[], Any] | None],
    feature_columns: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    train = frame[frame["season"].astype(str).isin(fold["train_seasons"])]
    calibration = frame[frame["season"].astype(str).isin(fold["calibration_seasons"])]
    test = frame[frame["season"].astype(str).isin(fold["test_seasons"])]
    train_rate = float(train[target].mean())
    baseline_probability = np.full(len(test), train_rate, dtype=float)
    predictions: dict[str, np.ndarray | None] = {"constant_train_rate": baseline_probability}
    reasons: dict[str, str] = {}
    for name, factory in variants.items():
        if factory is None:
            continue
        probability, reason = _model_probability(
            factory,
            train,
            test,
            target,
            feature_columns[name],
        )
        predictions[name] = probability
        if reason:
            reasons[name] = reason
    calibrated_name = "platt_expanded" if "platt_expanded" in variants else "platt_referee_enhanced"
    base_name = "expanded" if "expanded" in predictions else "referee_enhanced"
    if base_name in predictions and predictions[base_name] is not None:
        try:
            calibrator_model = variants[base_name]()
            calibrator_model.fit(train)
            calibration_probability = calibrator_model.predict_probability(calibration)
            calibrated = platt_calibrate(
                calibration_probability,
                calibration[target],
                pd.Series(predictions[base_name], index=test.index),
                c_value=1.0,
            ).to_numpy(dtype=float)
            predictions[calibrated_name] = calibrated
        except (ValueError, KeyError) as exc:
            reasons[calibrated_name] = str(exc)
            predictions[calibrated_name] = None
    rows: list[dict[str, Any]] = []
    for name, probability in predictions.items():
        row: dict[str, Any] = {
            "fold_id": fold["fold_id"],
            "market": fold["market"],
            "variant": name,
            "test_season": fold["test_seasons"][0],
            "train_rows": fold["train_rows"],
            "calibration_rows": fold["calibration_rows"],
            "test_rows": len(test),
            "coverage": float(len(test) / fold["test_rows"]) if fold["test_rows"] else 0.0,
            "feature_version": fold["feature_version"],
            "model_version": fold["model_version"],
            "status": "ok" if probability is not None else "inconclusive",
            "reason": reasons.get(name),
        }
        if probability is not None:
            row.update(
                _evaluate_predictions(
                    probability,
                    test[target],
                    baseline_probability,
                    expected_rows=len(test),
                )
            )
            row["probabilities"] = probability.tolist()
            row["actual"] = test[target].to_numpy(dtype=int).tolist()
            row["match_ids"] = test["match_id"].astype(str).tolist()
        else:
            row.update(
                {
                    "rows": len(test),
                    "accuracy": None,
                    "brier_score": None,
                    "log_loss": None,
                    "roc_auc": None,
                    "average_precision": None,
                    "brier_skill_score": None,
                    "log_loss_skill_score": None,
                    "ece_10": None,
                    "mean_probability": None,
                    "actual_rate": float(test[target].mean()) if len(test) else None,
                    "probabilities": None,
                    "actual": test[target].to_numpy(dtype=int).tolist(),
                    "match_ids": test["match_id"].astype(str).tolist(),
                }
            )
        rows.append(row)
    return rows, {"fold": fold, "train_rate": train_rate}


def _pooled_summary(rows: list[dict[str, Any]], market: str) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["market"] == market:
            by_variant.setdefault(row["variant"], []).append(row)
    summary: dict[str, Any] = {}
    for variant, variant_rows in by_variant.items():
        valid = [row for row in variant_rows if row["status"] == "ok"]
        summary[variant] = {
            "valid_folds": len(valid),
            "rows": sum(int(row["rows"]) for row in valid),
            "brier_mean": float(np.mean([row["brier_score"] for row in valid])) if valid else None,
            "log_loss_mean": float(np.mean([row["log_loss"] for row in valid])) if valid else None,
            "roc_auc_mean": float(
                np.mean([row["roc_auc"] for row in valid if row["roc_auc"] is not None])
            )
            if any(row["roc_auc"] is not None for row in valid)
            else None,
            "average_precision_mean": float(
                np.mean(
                    [
                        row["average_precision"]
                        for row in valid
                        if row["average_precision"] is not None
                    ]
                )
            )
            if any(row["average_precision"] is not None for row in valid)
            else None,
            "ece_10_mean": float(np.mean([row["ece_10"] for row in valid])) if valid else None,
        }
    return summary


def _gate(market: str, rows: list[dict[str, Any]], pooled: dict[str, Any]) -> dict[str, Any]:
    baseline = pooled.get("constant_train_rate", {})
    decisions: dict[str, Any] = {}
    for variant, result in pooled.items():
        if variant == "constant_train_rate":
            continue
        valid_rows = [
            row
            for row in rows
            if row["market"] == market and row["variant"] == variant and row["status"] == "ok"
        ]
        no_failures = len(valid_rows) == len(
            [row for row in rows if row["market"] == market and row["variant"] == variant]
        )
        reasons: list[str] = []
        if result["valid_folds"] < MIN_VALID_FOLDS:
            reasons.append("insufficient_valid_folds")
        if not no_failures:
            reasons.append("fold_failure_present")
        if (
            baseline.get("brier_mean") is None
            or result.get("brier_mean") is None
            or result["brier_mean"] > baseline["brier_mean"]
        ):
            reasons.append("mean_brier_not_better_or_equal")
        if (
            baseline.get("log_loss_mean") is None
            or result.get("log_loss_mean") is None
            or result["log_loss_mean"] > baseline["log_loss_mean"]
        ):
            reasons.append("mean_log_loss_not_better_or_equal")
        if (
            baseline.get("ece_10_mean") is not None
            and result.get("ece_10_mean") is not None
            and result["ece_10_mean"] > baseline["ece_10_mean"] + ECE_TOLERANCE
        ):
            reasons.append("ece_deterioration")
        decisions[variant] = {
            "status": "release" if not reasons else "no_release",
            "reasons": reasons,
            "thresholds_frozen_before_evaluation": True,
        }
    return decisions


def _load_test_summary() -> dict[str, Any] | None:
    path = ROOT / "reports" / "generated" / "cycle_32_test_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "fold_id",
        "market",
        "variant",
        "test_season",
        "train_rows",
        "calibration_rows",
        "test_rows",
        "coverage",
        "rows",
        "accuracy",
        "brier_score",
        "log_loss",
        "roc_auc",
        "average_precision",
        "brier_skill_score",
        "log_loss_skill_score",
        "ece_10",
        "mean_probability",
        "actual_rate",
        "status",
        "reason",
        "feature_version",
        "model_version",
    ]
    CSV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _write_manifest(
    path: Path, *, input_path: str, output_path: str, rows_before: int, rows_after: int
) -> None:
    manifest = build_manifest(
        input_path=input_path,
        input_sha256=sha256_file(ROOT / input_path),
        output_path=output_path,
        rows_before=rows_before,
        rows_after=rows_after,
        frame=pd.DataFrame({"kickoff_utc": []}),
        feature_version="cycle33-walk-forward-v1",
    )
    write_manifest(manifest, path)


def _prepare_fold_metadata(
    frame: pd.DataFrame, *, feature_version: str, model_version: str
) -> list[dict[str, Any]]:
    counts = frame.groupby(frame["season"].astype(str)).size().astype(int).to_dict()
    ranges = {
        str(season): (
            frame.loc[frame["season"].astype(str) == str(season), "kickoff_utc"].min().isoformat(),
            frame.loc[frame["season"].astype(str) == str(season), "kickoff_utc"].max().isoformat(),
        )
        for season in counts
    }
    folds = build_season_folds(
        counts.keys(),
        row_counts=counts,
        prediction_ranges=ranges,
        feature_version=feature_version,
        model_version=model_version,
        protected_seasons=PROTECTED_SEASONS,
        calibration_seasons=1,
    )
    return [{**fold.as_dict(), "market": ""} for fold in folds]


def _run_market(
    frame: pd.DataFrame,
    *,
    market: str,
    target: str,
    feature_version: str,
    model_version: str,
    variants: dict[str, Callable[[], Any] | None],
    feature_columns: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    metadata = _prepare_fold_metadata(
        frame, feature_version=feature_version, model_version=model_version
    )
    rows: list[dict[str, Any]] = []
    fold_records: list[dict[str, Any]] = []
    for fold in metadata:
        fold["market"] = market
        fold_rows, record = _fold_rows(
            frame,
            fold,
            target=target,
            variants=variants,
            feature_columns=feature_columns,
        )
        rows.extend(fold_rows)
        fold_records.append(record)
    pooled = _pooled_summary(rows, market)
    for variant, result in pooled.items():
        if variant == "constant_train_rate":
            continue
        candidate_rows = [
            row
            for row in rows
            if row["market"] == market and row["variant"] == variant and row["status"] == "ok"
        ]
        baseline_rows = {
            row["fold_id"]: row
            for row in rows
            if row["market"] == market
            and row["variant"] == "constant_train_rate"
            and row["status"] == "ok"
        }
        actual = (
            np.concatenate([np.asarray(row["actual"], dtype=int) for row in candidate_rows])
            if candidate_rows
            else np.array([], dtype=int)
        )
        candidate = (
            np.concatenate(
                [np.asarray(row["probabilities"], dtype=float) for row in candidate_rows]
            )
            if candidate_rows
            else np.array([], dtype=float)
        )
        baseline = (
            np.concatenate(
                [
                    np.asarray(baseline_rows[row["fold_id"]]["probabilities"], dtype=float)
                    for row in candidate_rows
                    if row["fold_id"] in baseline_rows
                ]
            )
            if candidate_rows
            else np.array([], dtype=float)
        )
        groups = (
            np.concatenate([np.asarray(row["match_ids"], dtype=str) for row in candidate_rows])
            if candidate_rows
            else np.array([], dtype=str)
        )
        result["pooled_bootstrap_vs_constant"] = _paired_bootstrap(
            actual, candidate, baseline, groups=groups
        )
        for row in candidate_rows:
            reference = baseline_rows.get(row["fold_id"])
            if reference is not None:
                row["bootstrap_vs_constant"] = _paired_bootstrap(
                    np.asarray(row["actual"], dtype=int),
                    np.asarray(row["probabilities"], dtype=float),
                    np.asarray(reference["probabilities"], dtype=float),
                    groups=np.asarray(row["match_ids"], dtype=str),
                    seed=BOOTSTRAP_SEED,
                )
    return rows, pooled, fold_records


def main() -> int:
    btts = pd.read_csv(PROCESSED / "epl_1516_2425_features.csv", parse_dates=["kickoff_utc"])
    cards_raw = pd.read_csv(PROCESSED / "epl_1516_2425.csv", parse_dates=["kickoff_utc"])
    cards = build_card_features(cards_raw).merge(
        cards_raw[["match_id", "season"]], on="match_id", how="left", validate="one_to_one"
    )
    btts = btts[
        btts["season"].astype(str).notna() & ~btts["season"].astype(str).isin(PROTECTED_SEASONS)
    ].copy()
    cards = cards[
        cards["season"].astype(str).notna() & ~cards["season"].astype(str).isin(PROTECTED_SEASONS)
    ].copy()
    btts_variants = {
        "expanded": lambda: BttsLogisticBaseline(feature_columns=FEATURE_COLUMNS),
        "legacy": lambda: BttsLogisticBaseline(feature_columns=LEGACY_FEATURE_COLUMNS),
        "platt_expanded": lambda: BttsLogisticBaseline(feature_columns=FEATURE_COLUMNS),
    }
    btts_columns = {
        "expanded": list(FEATURE_COLUMNS),
        "legacy": list(LEGACY_FEATURE_COLUMNS),
        "platt_expanded": list(FEATURE_COLUMNS),
    }
    cards_variants = {
        "referee_enhanced": lambda: TotalYellowCardsBaseline(feature_columns=CARD_FEATURE_COLUMNS),
        "legacy": lambda: TotalYellowCardsBaseline(feature_columns=LEGACY_CARD_FEATURE_COLUMNS),
        "platt_referee_enhanced": lambda: TotalYellowCardsBaseline(
            feature_columns=CARD_FEATURE_COLUMNS
        ),
    }
    cards_columns = {
        "referee_enhanced": list(CARD_FEATURE_COLUMNS),
        "legacy": list(LEGACY_CARD_FEATURE_COLUMNS),
        "platt_referee_enhanced": list(CARD_FEATURE_COLUMNS),
    }
    btts_rows, btts_pooled, btts_folds = _run_market(
        btts,
        market="btts",
        target="btts",
        feature_version="pre-match-rolling-v0.2",
        model_version="btts-logistic-v0.2",
        variants=btts_variants,
        feature_columns=btts_columns,
    )
    cards_rows, cards_pooled, cards_folds = _run_market(
        cards,
        market="cards",
        target="total_yellows_over_3_5",
        feature_version="card-team-referee-rolling-v0.2",
        model_version="cards-logistic-v0.2",
        variants=cards_variants,
        feature_columns=cards_columns,
    )
    rows = btts_rows + cards_rows
    _write_csv(rows)
    report = {
        "schema_version": "cycle33-walk-forward-v1",
        "cycle": 33,
        "protected_seasons": sorted(PROTECTED_SEASONS),
        "data_policy": "no_real_odds_no_financial_execution",
        "walk_forward_rule": (
            "expanding train seasons, immediately prior calibration season, "
            "next test season; no shuffle"
        ),
        "bootstrap": {
            "unit": "match_id",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence": 0.95,
        },
        "gate_constants": {"min_valid_folds": MIN_VALID_FOLDS, "ece_tolerance": ECE_TOLERANCE},
        "variants": {
            "btts": ["constant_train_rate", "legacy", "expanded", "platt_expanded"],
            "cards": [
                "constant_train_rate",
                "legacy",
                "referee_enhanced",
                "platt_referee_enhanced",
            ],
        },
        "markets": {
            "btts": {
                "folds": btts_folds,
                "pooled": btts_pooled,
                "decision_gate": _gate("btts", btts_rows, btts_pooled),
            },
            "cards": {
                "folds": cards_folds,
                "pooled": cards_pooled,
                "decision_gate": _gate("cards", cards_rows, cards_pooled),
            },
        },
        "fold_metrics": rows,
        "test_summary": _load_test_summary(),
        "economic_benchmark_status": "deferred",
        "financial_execution": False,
        "recommendation": False,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_json_value) + "\n", encoding="utf-8"
    )
    _write_manifest(
        REPORT.parent / "manifests" / "cycle_33_walk_forward.manifest.json",
        input_path="data/processed/epl_1516_2425_features.csv",
        output_path=str(REPORT),
        rows_before=len(btts),
        rows_after=len(rows),
    )
    _write_manifest(
        REPORT.parent / "manifests" / "cycle_33_fold_metrics.manifest.json",
        input_path="data/processed/epl_1516_2425_features.csv",
        output_path=str(CSV_OUTPUT),
        rows_before=len(btts),
        rows_after=len(rows),
    )
    print(json.dumps({"report": str(REPORT), "csv": str(CSV_OUTPUT), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
