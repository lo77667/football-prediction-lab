"""Evaluate the final unseen 2025/26 season as a future holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary, expected_calibration_error
from football_prediction_lab.features.cards import LEGACY_CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def metric_block(probability: pd.Series, target: pd.Series) -> dict[str, float | int]:
    result = evaluate_binary(probability, target).as_dict()
    result["ece_10"] = expected_calibration_error(probability, target, bins=10)
    return result


def evaluate_market(
    frame: pd.DataFrame,
    *,
    target: str,
    feature_columns: list[str],
    model_class: type,
    test_season: str,
    calibration_season: str,
) -> dict[str, object]:
    seasons = sorted(frame["season"].astype(str).unique())
    calibration_index = seasons.index(calibration_season)
    train_seasons = seasons[:calibration_index]
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    calibration = frame[frame["season"].astype(str) == calibration_season]
    test = frame[frame["season"].astype(str) == test_season]
    model = model_class(feature_columns=feature_columns).fit(train)
    base_calibration = model.predict_probability(calibration)
    base_test = model.predict_probability(test)
    calibrated = platt_calibrate(
        base_calibration,
        calibration[target],
        base_test,
        c_value=1.0,
    )
    constant_rate = float(pd.concat([train, calibration])[target].mean())
    constant = pd.Series(constant_rate, index=test.index)
    return {
        "target": target,
        "train_seasons": train_seasons,
        "calibration_season": calibration_season,
        "test_season": test_season,
        "base": metric_block(base_test, test[target]),
        "platt": metric_block(calibrated, test[target]),
        "constant_train_plus_calibration": metric_block(constant, test[target]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2526.csv")
    parser.add_argument("--features", default="data/processed/epl_1516_2526_features.csv")
    parser.add_argument("--test-season", default="2526")
    parser.add_argument("--calibration-season", default="2425")
    parser.add_argument("--output", default="reports/generated/future_2526_evaluation.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    normalized = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    btts_frame = pd.read_csv(root / args.features, parse_dates=["kickoff_utc"])
    cards_frame = build_card_features(normalized).merge(
        normalized[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    report = {
        "protocol": (
            "Train on seasons before calibration, fit Platt on 2425, test once on unseen 2526."
        ),
        "test_season": args.test_season,
        "btts": evaluate_market(
            btts_frame,
            target="btts",
            feature_columns=LEGACY_FEATURE_COLUMNS,
            model_class=BttsLogisticBaseline,
            test_season=args.test_season,
            calibration_season=args.calibration_season,
        ),
        "cards": evaluate_market(
            cards_frame,
            target="total_yellows_over_3_5",
            feature_columns=LEGACY_CARD_FEATURE_COLUMNS,
            model_class=TotalYellowCardsBaseline,
            test_season=args.test_season,
            calibration_season=args.calibration_season,
        ),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
