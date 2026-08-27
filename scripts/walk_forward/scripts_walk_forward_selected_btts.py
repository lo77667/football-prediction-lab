"""Walk-forward evaluation for the selected BTTS ablation family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline

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


def evaluate(
    frame: pd.DataFrame,
    feature_columns: list[str] | None,
    train_seasons: list[str],
    test_season: str,
) -> dict[str, object]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    if feature_columns is None:
        rate = float(train["btts"].mean())
        probability = pd.Series(rate, index=test.index)
    else:
        model = BttsLogisticBaseline(feature_columns=feature_columns).fit(train)
        probability = model.predict_probability(test)
    return evaluate_binary(probability, test["btts"]).as_dict() | {
        "test_season": test_season,
        "train_seasons": train_seasons,
    }


def average(results: list[dict[str, object]]) -> dict[str, float | int]:
    return {
        "folds": len(results),
        "rows": sum(int(result["rows"]) for result in results),
        "accuracy_mean": sum(float(result["accuracy"]) for result in results) / len(results),
        "brier_score_mean": sum(float(result["brier_score"]) for result in results) / len(results),
        "log_loss_mean": sum(float(result["log_loss"]) for result in results) / len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/walk_forward_selected_btts.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    seasons = sorted(frame["season"].astype(str).unique())
    variants = {
        "constant_train_rate": None,
        "legacy": LEGACY_FEATURE_COLUMNS,
        "rolling_plus_context": SELECTED_FEATURES,
    }
    results = {name: [] for name in variants}
    for index in range(1, len(seasons)):
        train_seasons = seasons[:index]
        test_season = seasons[index]
        for name, columns in variants.items():
            results[name].append(evaluate(frame, columns, train_seasons, test_season))
    report = {
        "rule": (
            "the selected family is evaluated across all future seasons "
            "without reselecting on each test fold"
        ),
        "variants": results,
        "summary": {name: average(values) for name, values in results.items()},
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
