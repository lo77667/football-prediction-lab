"""Nested walk-forward tuning with a validation season before each test season."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline

C_VALUES = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
WEIGHTS = (None, "balanced")


def select_model(model_type: str, train: pd.DataFrame, validation: pd.DataFrame):
    candidates = []
    for c_value in C_VALUES:
        for class_weight in WEIGHTS:
            model = _new_model(model_type, c_value, class_weight).fit(train)
            probability = model.predict_probability(validation)
            target = _target(model_type, validation)
            metrics = evaluate_binary(probability, target).as_dict()
            candidates.append((metrics["brier_score"], metrics["log_loss"], c_value, class_weight))
    _, _, c_value, class_weight = min(candidates)
    return c_value, class_weight


def _new_model(model_type: str, c_value: float, class_weight: str | None):
    if model_type == "btts":
        return BttsLogisticBaseline(c_value=c_value, class_weight=class_weight)
    return TotalYellowCardsBaseline(c_value=c_value, class_weight=class_weight)


def _target(model_type: str, frame: pd.DataFrame) -> pd.Series:
    return frame["btts"] if model_type == "btts" else frame["total_yellows_over_3_5"]


def run_walk_forward(
    frame: pd.DataFrame,
    model_type: str,
    feature_columns: list[str],
) -> list[dict[str, object]]:
    seasons = sorted(frame["season"].astype(str).unique())
    folds: list[dict[str, object]] = []
    for index in range(2, len(seasons)):
        validation_season = seasons[index - 1]
        test_season = seasons[index]
        train_seasons = seasons[: index - 1]
        validation = frame[frame["season"].astype(str) == validation_season]
        train = frame[frame["season"].astype(str).isin(train_seasons)]
        test = frame[frame["season"].astype(str) == test_season]
        c_value, class_weight = select_model(model_type, train, validation)
        final_train = pd.concat([train, validation], ignore_index=True)
        model = _new_model(model_type, c_value, class_weight).fit(final_train)
        probability = model.predict_probability(test)
        folds.append(
            evaluate_binary(probability, _target(model_type, test)).as_dict()
            | {
                "validation_season": validation_season,
                "test_season": test_season,
                "train_seasons": train_seasons,
                "c_value": c_value,
                "class_weight": class_weight,
            }
        )
    return folds


def summarize(folds: list[dict[str, object]]) -> dict[str, float | int]:
    return {
        "folds": len(folds),
        "rows": sum(int(fold["rows"]) for fold in folds),
        "accuracy_mean": sum(float(fold["accuracy"]) for fold in folds) / len(folds),
        "brier_score_mean": sum(float(fold["brier_score"]) for fold in folds) / len(folds),
        "log_loss_mean": sum(float(fold["log_loss"]) for fold in folds) / len(folds),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425_features.csv")
    parser.add_argument("--cards-input", default="data/processed/epl_1819_2425.csv")
    parser.add_argument("--output", default="reports/generated/nested_walk_forward_results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    btts_frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    matches = pd.read_csv(root / args.cards_input, parse_dates=["kickoff_utc"])
    cards_frame = build_card_features(matches).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    btts_folds = run_walk_forward(btts_frame, "btts", FEATURE_COLUMNS)
    cards_folds = run_walk_forward(cards_frame, "cards", CARD_FEATURE_COLUMNS)
    results = {
        "rule": "the immediately preceding season is validation; test season remains untouched",
        "btts": {"folds": btts_folds, "summary": summarize(btts_folds)},
        "cards": {"folds": cards_folds, "summary": summarize(cards_folds)},
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
