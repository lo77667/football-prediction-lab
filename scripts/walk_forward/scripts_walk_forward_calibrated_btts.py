"""Nested walk-forward calibration for the selected BTTS feature family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scripts_calibrate_btts_holdout import SELECTED_FEATURES
from sklearn.isotonic import IsotonicRegression

from football_prediction_lab.evaluation.metrics import evaluate_binary, expected_calibration_error
from football_prediction_lab.models.btts import BttsLogisticBaseline


def evaluate_fold(
    frame: pd.DataFrame,
    train_seasons: list[str],
    calibration_season: str,
    test_season: str,
) -> dict[str, object]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    calibration = frame[frame["season"].astype(str) == calibration_season]
    test = frame[frame["season"].astype(str) == test_season]
    model = BttsLogisticBaseline(feature_columns=SELECTED_FEATURES).fit(train)
    calibration_probability = model.predict_probability(calibration)
    test_probability = model.predict_probability(test)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(
        calibration_probability, calibration["btts"]
    )
    calibrated = pd.Series(calibrator.predict(test_probability), index=test.index)
    return {
        "test_season": test_season,
        "train_seasons": train_seasons,
        "calibration_season": calibration_season,
        "base": evaluate_binary(test_probability, test["btts"]).as_dict(),
        "base_ece_10": expected_calibration_error(test_probability, test["btts"], bins=10),
        "calibrated": evaluate_binary(calibrated, test["btts"]).as_dict(),
        "calibrated_ece_10": expected_calibration_error(calibrated, test["btts"], bins=10),
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
    parser.add_argument("--input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/walk_forward_calibrated_btts.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    seasons = sorted(frame["season"].astype(str).unique())
    folds = []
    for index in range(2, len(seasons)):
        folds.append(
            evaluate_fold(
                frame,
                seasons[: index - 1],
                seasons[index - 1],
                seasons[index],
            )
        )
    report = {
        "rule": (
            "train on earlier seasons, calibrate on the immediately prior season, "
            "test on the next season"
        ),
        "folds": folds,
        "summary": {
            "base": average(folds, "base"),
            "calibrated": average(folds, "calibrated"),
        },
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
