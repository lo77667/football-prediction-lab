"""Nested walk-forward Platt calibration for the cards market."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary, expected_calibration_error
from football_prediction_lab.features.cards import LEGACY_CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def evaluate_fold(
    frame: pd.DataFrame,
    train_seasons: list[str],
    calibration_seasons: list[str],
    test_season: str,
    c_value: float,
) -> dict[str, object]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    calibration = frame[frame["season"].astype(str).isin(calibration_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = TotalYellowCardsBaseline(feature_columns=LEGACY_CARD_FEATURE_COLUMNS).fit(train)
    calibration_probability = model.predict_probability(calibration)
    test_probability = model.predict_probability(test)
    calibrated = platt_calibrate(
        calibration_probability,
        calibration["total_yellows_over_3_5"],
        test_probability,
        c_value=c_value,
    )
    target = test["total_yellows_over_3_5"]
    return {
        "test_season": test_season,
        "train_seasons": train_seasons,
        "calibration_seasons": calibration_seasons,
        "base": evaluate_binary(test_probability, target).as_dict(),
        "base_ece_10": expected_calibration_error(test_probability, target, bins=10),
        "calibrated": evaluate_binary(calibrated, target).as_dict(),
        "calibrated_ece_10": expected_calibration_error(calibrated, target, bins=10),
    }


def average(results: list[dict[str, object]], key: str) -> dict[str, float | int]:
    metrics = [result[key] for result in results]
    return {
        "folds": len(metrics),
        "rows": sum(int(metric["rows"]) for metric in metrics),
        "brier_score_mean": sum(float(metric["brier_score"]) for metric in metrics) / len(metrics),
        "log_loss_mean": sum(float(metric["log_loss"]) for metric in metrics) / len(metrics),
        "ece_10_mean": sum(float(result[f"{key}_ece_10"]) for result in results) / len(metrics),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--output", default="reports/generated/walk_forward_platt_cards.json")
    parser.add_argument("--c-value", type=float, default=1.0)
    parser.add_argument("--calibration-seasons", type=int, default=1)
    args = parser.parse_args()
    if args.c_value <= 0 or args.calibration_seasons < 1:
        parser.error("c-value must be positive and calibration-seasons must be positive")

    root = Path(__file__).resolve().parent
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    frame = build_card_features(matches).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    seasons = sorted(frame["season"].astype(str).unique())
    folds = [
        evaluate_fold(
            frame,
            seasons[: index - args.calibration_seasons],
            seasons[index - args.calibration_seasons : index],
            seasons[index],
            args.c_value,
        )
        for index in range(args.calibration_seasons + 1, len(seasons))
    ]
    report = {
        "rule": (
            "fit cards base on earlier seasons, calibrate on prior seasons, "
            "test on next season"
        ),
        "market": "total_yellows_over_3_5",
        "feature_set": "legacy",
        "c_value": args.c_value,
        "calibration_seasons_count": args.calibration_seasons,
        "folds": folds,
        "summary": {"base": average(folds, "base"), "calibrated": average(folds, "calibrated")},
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
