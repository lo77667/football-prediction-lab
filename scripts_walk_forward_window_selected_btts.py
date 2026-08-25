"""Nested walk-forward BTTS evaluation with validation-only window selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.pre_match import (
    build_pre_match_features,
    feature_columns_for_window,
)
from football_prediction_lab.learning.window_selection import select_window
from football_prediction_lab.models.btts import BttsLogisticBaseline

CANDIDATE_WINDOWS = (3, 5, 10)


def evaluate_model(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_seasons: list[str],
    test_season: str,
) -> dict[str, float | int | str]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = BttsLogisticBaseline(feature_columns=feature_columns).fit(train)
    return evaluate_binary(model.predict_probability(test), test["btts"]).as_dict() | {
        "test_season": test_season,
        "train_seasons": train_seasons,
    }


def evaluate_nested_window_fold(
    frames: dict[int, pd.DataFrame],
    train_seasons: list[str],
    validation_season: str,
    test_season: str,
) -> dict[str, object]:
    validation_scores: dict[int, dict[str, float]] = {}
    for window, frame in frames.items():
        validation = evaluate_model(
            frame,
            feature_columns_for_window(window),
            train_seasons,
            validation_season,
        )
        validation_scores[window] = {
            "brier_score": float(validation["brier_score"]),
            "log_loss": float(validation["log_loss"]),
        }

    selection = select_window(validation_scores)
    selected_frame = frames[selection.window]
    test = evaluate_model(
        selected_frame,
        feature_columns_for_window(selection.window),
        train_seasons + [validation_season],
        test_season,
    )
    return {
        "test_season": test_season,
        "validation_season": validation_season,
        "train_seasons": train_seasons,
        "candidate_windows": list(CANDIDATE_WINDOWS),
        "validation_scores": validation_scores,
        "selected_window": selection.window,
        "selected_validation_brier_score": selection.validation_brier_score,
        "selected_validation_log_loss": selection.validation_log_loss,
        "test": test,
    }


def average_test_metrics(folds: list[dict[str, object]]) -> dict[str, float | int]:
    metrics = [fold["test"] for fold in folds]
    summary: dict[str, float | int] = {
        "folds": len(folds),
        "rows": sum(int(metric["rows"]) for metric in metrics),
    }
    for name in ("accuracy", "brier_score", "log_loss"):
        values = [float(metric[name]) for metric in metrics]
        summary[f"{name}_mean"] = sum(values) / len(values)
        summary[f"{name}_min"] = min(values)
        summary[f"{name}_max"] = max(values)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument(
        "--output",
        default="reports/generated/walk_forward_window_selected_btts_ten_seasons.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    seasons = sorted(matches["season"].astype(str).unique())
    frames = {
        window: build_pre_match_features(matches, window=window).merge(
            matches[["match_id", "season"]],
            on="match_id",
            how="left",
            validate="one_to_one",
        )
        for window in CANDIDATE_WINDOWS
    }
    folds = [
        evaluate_nested_window_fold(
            frames,
            seasons[:index - 1],
            seasons[index - 1],
            seasons[index],
        )
        for index in range(2, len(seasons))
    ]
    result = {
        "seasons": seasons,
        "candidate_windows": list(CANDIDATE_WINDOWS),
        "protocol": (
            "For each test season, choose one window on the immediately prior validation "
            "season using Brier then Log Loss; refit on train plus validation; evaluate once "
            "on the next test season. No test metric participates in selection."
        ),
        "folds": folds,
        "summary": average_test_metrics(folds),
        "selected_window_counts": {
            str(window): sum(fold["selected_window"] == window for fold in folds)
            for window in CANDIDATE_WINDOWS
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
