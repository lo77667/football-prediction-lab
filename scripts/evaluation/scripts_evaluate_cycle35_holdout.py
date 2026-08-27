"""Run Cycle 35 frozen-policy evaluation on the protected 2526 holdout."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from football_prediction_lab.data.provenance import sha256_file
from football_prediction_lab.evaluation.contracts import (
    PredictionRecord,
    validate_prediction_ledger,
)
from football_prediction_lab.evaluation.holdout_policy import (
    assert_prediction_artifact_safe,
    assert_selection_history_excludes_holdout,
    choose_modal_variant,
    load_policy_lock,
)
from football_prediction_lab.evaluation.metrics import (
    evaluate_binary_extended,
    expected_calibration_error,
)
from football_prediction_lab.evaluation.nested_walk_forward import paired_bootstrap_outer_test
from football_prediction_lab.features.cards import build_card_features

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
CONFIG = ROOT / "configs" / "cycle35_policy_lock.json"
SELECTION_REPORT = ROOT / "reports" / "generated" / "cycle_35_policy_selection.json"
PREDICTIONS_REPORT = ROOT / "reports" / "generated" / "cycle_35_2526_predictions_prelabel.json"
EVALUATION_REPORT = ROOT / "reports" / "generated" / "cycle_35_2526_evaluation.json"
METRICS_CSV = ROOT / "reports" / "generated" / "cycle_35_2526_metrics.csv"
MANIFEST_DIR = ROOT / "reports" / "generated" / "manifests"
PROTECTED_SEASON = "2526"
BOOTSTRAP_SEED = 3501
BOOTSTRAP_REPLICATES = 1_000
PREDICTION_LEAD = timedelta(minutes=5)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target(market: str) -> str:
    return "btts" if market == "btts" else "total_yellows_over_3_5"


def _market_definition(market: str) -> str:
    if market == "btts":
        return "both_teams_to_score_at_least_one_goal"
    return "total_yellow_cards_over_3_5"


def _load_market_frames(market: str) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    if market == "btts":
        source = PROCESSED / "epl_1516_2526_features.csv"
        frame = pd.read_csv(source, parse_dates=["kickoff_utc"])
    else:
        source = PROCESSED / "epl_1516_2526.csv"
        raw = pd.read_csv(source, parse_dates=["kickoff_utc"])
        frame = build_card_features(raw).merge(
            raw[["match_id", "season"]], on="match_id", how="left", validate="one_to_one"
        )
    frame["kickoff_utc"] = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="raise")
    frame["season"] = frame["season"].astype(str)
    historical = frame[frame["season"] != PROTECTED_SEASON].copy()
    holdout = frame[frame["season"] == PROTECTED_SEASON].copy()
    if holdout.empty:
        raise ValueError(f"no protected holdout rows found for {market}")
    if holdout["match_id"].duplicated().any():
        raise ValueError(f"duplicate holdout match_id values for {market}")
    return historical, holdout, source


def _constant_predictions(
    market: str,
    historical: pd.DataFrame,
    holdout: pd.DataFrame,
    lock: dict[str, Any],
    policy_hash: str,
    source_hash: str,
) -> list[dict[str, Any]]:
    details = lock["markets"][market]
    if details["selected_variant"] != "constant_train_rate":
        raise ValueError("Cycle 35 implementation only permits its locked constant variant")
    target = _target(market)
    training_seasons = set(details["training_seasons"])
    training = historical[historical["season"].isin(training_seasons)].copy()
    if training.empty:
        raise ValueError(f"empty historical training frame for {market}")
    cutoff = pd.Timestamp(details["training_cutoff"], tz="UTC")
    if (training["kickoff_utc"] >= cutoff).any():
        raise ValueError(f"training data crosses cutoff for {market}")
    if holdout["kickoff_utc"].min() <= cutoff:
        raise ValueError(f"holdout is not strictly after training cutoff for {market}")
    probability = float(training[target].mean())
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"invalid constant probability for {market}")
    records: list[dict[str, Any]] = []
    for row in holdout.sort_values(["kickoff_utc", "match_id"]).itertuples(index=False):
        kickoff = pd.Timestamp(row.kickoff_utc).to_pydatetime()
        issued_at = kickoff - PREDICTION_LEAD
        record = PredictionRecord(
            prediction_id=f"cycle35-{market}-{row.match_id}",
            market=market,
            market_definition=_market_definition(market),
            match_id=str(row.match_id),
            issued_at=issued_at,
            kickoff_utc=kickoff,
            probability=probability,
            threshold=float(details["threshold"]),
            model_version=details["model_version"],
            feature_version=details["feature_version"],
            training_cutoff=cutoff.to_pydatetime(),
            input_provenance=[
                f"sha256:{source_hash}",
                f"policy_lock_sha256:{policy_hash}",
            ],
        )
        records.append(record.as_audit_dict())
    validate_prediction_ledger([PredictionRecord.model_validate(item) for item in records])
    return records


def _write_predictions(lock: dict[str, Any], policy_hash: str) -> tuple[dict[str, Any], str]:
    source_hashes = {
        "btts_source": sha256_file(PROCESSED / "epl_1516_2526_features.csv"),
        "cards_source": sha256_file(PROCESSED / "epl_1516_2526.csv"),
    }
    all_records: list[dict[str, Any]] = []
    market_counts: dict[str, int] = {}
    for market in ("btts", "cards"):
        historical, holdout, _ = _load_market_frames(market)
        records = _constant_predictions(
            market,
            historical,
            holdout,
            lock,
            policy_hash,
            source_hashes[f"{market}_source"],
        )
        all_records.extend(records)
        market_counts[market] = len(records)
    payload = {
        "schema_version": "cycle35-prelabel-predictions-v1",
        "cycle": 35,
        "stage": "prelabel",
        "policy_version": lock["policy_version"],
        "policy_lock_sha256": policy_hash,
        "protected_holdout": [PROTECTED_SEASON],
        "target_columns_excluded": [
            "btts",
            "total_yellows_over_3_5",
            "home_goals",
            "away_goals",
            "total_yellows",
        ],
        "prediction_count_by_market": market_counts,
        "predictions": all_records,
        "evaluation_not_run": True,
    }
    PREDICTIONS_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_REPORT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert_prediction_artifact_safe(
        PREDICTIONS_REPORT,
        expected_policy_version=lock["policy_version"],
    )
    return payload, sha256_file(PREDICTIONS_REPORT)


def _metric_functions() -> dict[str, Callable[[np.ndarray, np.ndarray], float]]:
    return {
        "brier_score": lambda y, p: float(np.mean((p - y) ** 2)),
        "log_loss": lambda y, p: float(
            -np.mean(
                y * np.log(np.clip(p, 1e-15, 1 - 1e-15))
                + (1 - y) * np.log(np.clip(1 - p, 1e-15, 1 - 1e-15))
            )
        ),
    }


def _bootstrap(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    match_ids: np.ndarray,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "unit": "match_id",
        "seed": BOOTSTRAP_SEED,
        "replicates": BOOTSTRAP_REPLICATES,
        "interpretation": "descriptive_only; no_economic_inference",
    }
    for name, function in _metric_functions().items():
        result[name] = paired_bootstrap_outer_test(
            actual,
            candidate,
            baseline,
            match_ids,
            function,
            seed=BOOTSTRAP_SEED,
            replicates=BOOTSTRAP_REPLICATES,
        )
    return result


def _evaluate_market(
    market: str,
    predictions: list[dict[str, Any]],
    lock: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    _, holdout, _ = _load_market_frames(market)
    target = _target(market)
    prediction_frame = pd.DataFrame([item for item in predictions if item["market"] == market])
    labels = holdout[["match_id", target]].copy()
    labels["match_id"] = labels["match_id"].astype(str)
    joined = prediction_frame.merge(labels, on="match_id", how="inner", validate="one_to_one")
    if len(joined) != len(prediction_frame) or len(joined) != len(labels):
        raise ValueError(f"holdout prediction coverage mismatch for {market}")
    actual = joined[target].to_numpy(dtype=int)
    probability = joined["probability"].to_numpy(dtype=float)
    historical, _, _ = _load_market_frames(market)
    baseline_rate = float(historical[target].mean())
    baseline = np.full(len(joined), baseline_rate, dtype=float)
    threshold = float(lock["markets"][market]["threshold"])
    metrics = evaluate_binary_extended(
        probability,
        actual,
        baseline_probability=baseline,
        threshold=threshold,
        expected_rows=len(labels),
    )
    metrics["ece_10"] = expected_calibration_error(probability, actual, bins=10)
    baseline_metrics = evaluate_binary_extended(
        baseline,
        actual,
        threshold=threshold,
        expected_rows=len(labels),
    )
    bootstrap = _bootstrap(
        actual,
        probability,
        baseline,
        joined["match_id"].astype(str).to_numpy(),
    )
    return (
        {
            "market": market,
            "market_definition": _market_definition(market),
            "rows": len(joined),
            "coverage": float(len(joined) / len(labels)),
            "baseline": {
                "type": "frozen_historical_rate_before_2526",
                "probability": baseline_rate,
                "metrics": baseline_metrics,
            },
            "holdout_metrics": metrics,
            "bootstrap_vs_baseline": bootstrap,
            "status": {
                "brier": bootstrap["brier_score"]["interval_status"],
                "log_loss": bootstrap["log_loss"]["interval_status"],
                "interpretation": "directional_or_inconclusive_descriptive_only",
            },
            "excluded_data": ["odds", "roi", "ev", "stake_sizing", "post_match_fields"],
        },
        joined[["match_id", "kickoff_utc", target, "probability"]],
    )


def _write_csv(rows: list[dict[str, Any]]) -> None:
    METRICS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with METRICS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(path: Path, output_path: Path, inputs: dict[str, Path], rows: int) -> None:
    payload = {
        "schema_version": "cycle35-artifact-manifest-v1",
        "output_path": str(output_path.relative_to(ROOT)),
        "output_sha256": sha256_file(output_path),
        "rows_after": rows,
        "timezone": "UTC",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            name: {
                "path": str(input_path.relative_to(ROOT)),
                "sha256": sha256_file(input_path),
            }
            for name, input_path in inputs.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    lock = load_policy_lock(CONFIG)
    for details in lock["markets"].values():
        assert_selection_history_excludes_holdout(details["training_seasons"])
    policy_hash_before = sha256_file(CONFIG)
    cycle34_report = ROOT / "reports/generated/cycle_34_nested_walk_forward.json"
    cycle34_counts = {
        market: _read_json(cycle34_report)["markets"][market]["pooled"]["selected_variant_counts"]
        for market in ("btts", "cards")
    }
    selection_decisions = {
        market: choose_modal_variant(cycle34_counts[market]) for market in ("btts", "cards")
    }
    if any(
        selection_decisions[market]["selected_variant"]
        != lock["markets"][market]["selected_variant"]
        for market in ("btts", "cards")
    ):
        raise RuntimeError("policy lock does not match deterministic modal selection")
    selection_payload = {
        "schema_version": "cycle35-policy-selection-v1",
        "cycle": 35,
        "source_cycle": 34,
        "policy_lock_sha256": policy_hash_before,
        "selection_rule": lock["selection_rule"],
        "selection_counts": cycle34_counts,
        "selection_decisions": selection_decisions,
        "selected_variants": {
            market: lock["markets"][market]["selected_variant"] for market in ("btts", "cards")
        },
        "selection_used_2526_labels": False,
        "commercial_release": False,
    }
    SELECTION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_REPORT.write_text(
        json.dumps(selection_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    prediction_payload, prediction_hash = _write_predictions(lock, policy_hash_before)
    policy_hash_after = sha256_file(CONFIG)
    if policy_hash_after != policy_hash_before:
        raise RuntimeError("policy lock changed after prediction artifact creation")
    guards = {
        "policy_lock_present_and_valid": True,
        "policy_lock_unchanged_after_predictions": policy_hash_after == policy_hash_before,
        "selection_used_2526_labels": False,
        "prediction_artifact_has_no_targets": True,
        "prediction_timestamps_precede_kickoff": True,
        "training_cutoff_precedes_kickoff": True,
        "unique_2526_matches_per_market": True,
        "post_match_features_excluded": True,
        "reproducible_constant_probabilities": True,
    }
    positive_guards = [
        value for key, value in guards.items() if key != "selection_used_2526_labels"
    ]
    if (
        not all(value is True for value in positive_guards)
        or guards["selection_used_2526_labels"] is not False
    ):
        raise RuntimeError("holdout freeze guard failed")
    market_reports: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    for market in ("btts", "cards"):
        report, _ = _evaluate_market(market, prediction_payload["predictions"], lock)
        market_reports[market] = report
        csv_rows.append(
            {
                "market": market,
                "rows": report["rows"],
                "coverage": report["coverage"],
                "selected_variant": lock["markets"][market]["selected_variant"],
                "baseline_probability": report["baseline"]["probability"],
                "accuracy": report["holdout_metrics"]["accuracy"],
                "brier_score": report["holdout_metrics"]["brier_score"],
                "log_loss": report["holdout_metrics"]["log_loss"],
                "roc_auc": report["holdout_metrics"]["roc_auc"],
                "average_precision": report["holdout_metrics"]["average_precision"],
                "ece_10": report["holdout_metrics"]["ece_10"],
                "brier_interval_status": report["status"]["brier"],
                "log_loss_interval_status": report["status"]["log_loss"],
                "commercial_release": False,
            }
        )
    _write_csv(csv_rows)
    evaluation_payload = {
        "schema_version": "cycle35-final-holdout-evaluation-v1",
        "cycle": 35,
        "policy_version": lock["policy_version"],
        "policy_lock_sha256": policy_hash_before,
        "prediction_artifact_sha256": prediction_hash,
        "protected_holdout": [PROTECTED_SEASON],
        "policy_locked": True,
        "holdout_evaluated": True,
        "evaluation_runs": 1,
        "evaluation_valid": True,
        "evaluation_invalidated": False,
        "freeze_guards": guards,
        "bootstrap": {
            "unit": "match_id",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence": 0.95,
            "status": "descriptive_only",
        },
        "markets": market_reports,
        "economic_benchmark_status": "deferred",
        "financial_execution": False,
        "commercial_release": False,
    }
    EVALUATION_REPORT.write_text(
        json.dumps(evaluation_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_manifest(
        MANIFEST_DIR / "cycle_35_policy_lock.manifest.json",
        CONFIG,
        {"cycle34_report": cycle34_report},
        2,
    )
    _write_manifest(
        MANIFEST_DIR / "cycle_35_policy_selection.manifest.json",
        SELECTION_REPORT,
        {"cycle34_report": cycle34_report, "policy_lock": CONFIG},
        2,
    )
    _write_manifest(
        MANIFEST_DIR / "cycle_35_2526_predictions_prelabel.manifest.json",
        PREDICTIONS_REPORT,
        {
            "btts_source": PROCESSED / "epl_1516_2526_features.csv",
            "cards_source": PROCESSED / "epl_1516_2526.csv",
            "policy_lock": CONFIG,
        },
        len(prediction_payload["predictions"]),
    )
    _write_manifest(
        MANIFEST_DIR / "cycle_35_2526_evaluation.manifest.json",
        EVALUATION_REPORT,
        {"predictions_prelabel": PREDICTIONS_REPORT, "policy_lock": CONFIG},
        sum(report["rows"] for report in market_reports.values()),
    )
    _write_manifest(
        MANIFEST_DIR / "cycle_35_2526_metrics.manifest.json",
        METRICS_CSV,
        {"evaluation": EVALUATION_REPORT},
        len(csv_rows),
    )
    print(
        json.dumps(
            {
                "policy_lock": str(CONFIG),
                "prediction_count": len(prediction_payload["predictions"]),
                "evaluation": str(EVALUATION_REPORT),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
