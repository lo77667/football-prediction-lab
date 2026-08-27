"""Calibrate one BTTS feature family on validation only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.isotonic import IsotonicRegression

from football_prediction_lab.evaluation.metrics import evaluate_binary, expected_calibration_error
from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split

SELECTED_FEATURES = [
    "home_avg_scored_5",
    "home_avg_conceded_5",
    "home_btts_rate_5",
    "away_avg_scored_5",
    "away_avg_conceded_5",
    "away_btts_rate_5",
    "home_matches_before",
    "away_matches_before",
    "home_avg_scored_10",
    "home_avg_conceded_10",
    "home_btts_rate_10",
    "away_avg_scored_10",
    "away_avg_conceded_10",
    "away_btts_rate_10",
    "home_points_avg_5",
    "away_points_avg_5",
    "home_shots_on_target_avg_5",
    "away_shots_on_target_avg_5",
    "home_corners_avg_5",
    "away_corners_avg_5",
    "home_clean_sheet_rate_5",
    "away_clean_sheet_rate_5",
    "home_points_avg_10",
    "away_points_avg_10",
    "home_shots_on_target_avg_10",
    "away_shots_on_target_avg_10",
    "home_corners_avg_10",
    "away_corners_avg_10",
    "home_clean_sheet_rate_10",
    "away_clean_sheet_rate_10",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/btts_calibration_holdout.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    split = temporal_split(frame)
    model = BttsLogisticBaseline(feature_columns=SELECTED_FEATURES).fit(split.train)
    validation_probability = model.predict_probability(split.validation)
    test_probability = model.predict_probability(split.test)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(
        validation_probability, split.validation["btts"]
    )
    calibrated_test = pd.Series(
        calibrator.predict(test_probability), index=split.test.index
    )
    result = {
        "calibration_rule": (
            "fit isotonic mapping on validation probabilities only; "
            "evaluate once on future test"
        ),
        "base_test": evaluate_binary(test_probability, split.test["btts"]).as_dict(),
        "base_test_ece_10": expected_calibration_error(
            test_probability, split.test["btts"], bins=10
        ),
        "calibrated_test": evaluate_binary(
            calibrated_test, split.test["btts"]
        ).as_dict(),
        "calibrated_test_ece_10": expected_calibration_error(
            calibrated_test, split.test["btts"], bins=10
        ),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
