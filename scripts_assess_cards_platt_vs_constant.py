"""Compare calibrated cards probabilities with a constant cards rate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.features.cards import build_card_features
from scripts_walk_forward import evaluate_constant


def average_metrics(results: list[dict[str, object]]) -> dict[str, float | int]:
    summary: dict[str, float | int] = {
        "folds": len(results),
        "rows": sum(int(result["rows"]) for result in results),
    }
    for name in ("accuracy", "brier_score", "log_loss"):
        values = [float(result[name]) for result in results]
        summary[f"{name}_mean"] = sum(values) / len(values)
        summary[f"{name}_min"] = min(values)
        summary[f"{name}_max"] = max(values)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument(
        "--platt-report",
        default="reports/generated/walk_forward_platt_cards_legacy_ten_seasons.json",
    )
    parser.add_argument(
        "--output",
        default="reports/generated/platt_cards_vs_constant_decision.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    report = json.loads((root / args.platt_report).read_text(encoding="utf-8"))
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    card_frame = build_card_features(matches).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    seasons = sorted(card_frame["season"].astype(str).unique())
    constant_folds = []
    for index in range(2, len(seasons)):
        constant_folds.append(
            evaluate_constant(
                card_frame,
                "total_yellows_over_3_5",
                seasons[:index],
                seasons[index],
            )
        )
    calibrated_folds = [fold["calibrated"] for fold in report["folds"]]
    baseline = average_metrics(constant_folds)
    candidate = report["summary"]["calibrated"]
    result = {
        "protocol": (
            "Cards Platt and constant use the same eight test seasons; constant uses "
            "train through the immediately prior calibration season."
        ),
        "baseline_constant_train_rate": baseline,
        "candidate_platt_cards": candidate,
        "fold_comparison": {
            "brier_wins": sum(
                float(candidate_fold["brier_score"]) < float(constant_fold["brier_score"])
                for candidate_fold, constant_fold in zip(calibrated_folds, constant_folds)
            ),
            "log_loss_wins": sum(
                float(candidate_fold["log_loss"]) < float(constant_fold["log_loss"])
                for candidate_fold, constant_fold in zip(calibrated_folds, constant_folds)
            ),
            "joint_probability_metric_wins": sum(
                float(candidate_fold["brier_score"]) < float(constant_fold["brier_score"])
                and float(candidate_fold["log_loss"]) < float(constant_fold["log_loss"])
                for candidate_fold, constant_fold in zip(calibrated_folds, constant_folds)
            ),
            "total_folds": len(constant_folds),
        },
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
