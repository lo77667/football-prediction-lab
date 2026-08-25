"""Run season-by-season walk-forward evaluation for both research markets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.cards import (
    CARD_FEATURE_COLUMNS,
    LEGACY_CARD_FEATURE_COLUMNS,
    build_card_features,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def evaluate_btts(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_seasons: list[str],
    test_season: str,
) -> dict[str, float | int | str]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = BttsLogisticBaseline(feature_columns=feature_columns).fit(train)
    probability = model.predict_probability(test)
    return evaluate_binary(probability, test["btts"]).as_dict() | {
        "test_season": test_season,
        "train_seasons": train_seasons,
    }


def evaluate_constant(
    frame: pd.DataFrame,
    target_column: str,
    train_seasons: list[str],
    test_season: str,
) -> dict[str, float | int | str]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    train_rate = float(train[target_column].mean())
    probability = pd.Series(train_rate, index=test.index)
    return evaluate_binary(probability, test[target_column]).as_dict() | {
        "test_season": test_season,
        "train_seasons": train_seasons,
        "train_rate": train_rate,
    }


def evaluate_cards(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_seasons: list[str],
    test_season: str,
) -> dict[str, float | int | str]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = TotalYellowCardsBaseline(feature_columns=feature_columns).fit(train)
    probability = model.predict_probability(test)
    return evaluate_binary(
        probability, test["total_yellows_over_3_5"]
    ).as_dict() | {
        "test_season": test_season,
        "train_seasons": train_seasons,
    }


def average_metrics(results: list[dict[str, object]]) -> dict[str, float | int]:
    return {
        "folds": len(results),
        "rows": sum(int(result["rows"]) for result in results),
        "accuracy_mean": sum(float(result["accuracy"]) for result in results) / len(results),
        "brier_score_mean": sum(float(result["brier_score"]) for result in results) / len(results),
        "log_loss_mean": sum(float(result["log_loss"]) for result in results) / len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425_features.csv")
    parser.add_argument("--cards-input", default="data/processed/epl_1819_2425.csv")
    parser.add_argument("--output", default="reports/generated/walk_forward_results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    btts_frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    seasons = sorted(btts_frame["season"].astype(str).unique())
    btts_results: dict[str, list[dict[str, object]]] = {
        "constant_train_rate": [],
        "legacy": [],
        "expanded": [],
    }
    for index in range(1, len(seasons)):
        train_seasons = seasons[:index]
        test_season = seasons[index]
        btts_results["constant_train_rate"].append(
            evaluate_constant(btts_frame, "btts", train_seasons, test_season)
        )
        btts_results["legacy"].append(
            evaluate_btts(btts_frame, LEGACY_FEATURE_COLUMNS, train_seasons, test_season)
        )
        btts_results["expanded"].append(
            evaluate_btts(btts_frame, FEATURE_COLUMNS, train_seasons, test_season)
        )

    matches = pd.read_csv(root / args.cards_input, parse_dates=["kickoff_utc"])
    cards_frame = build_card_features(matches)
    cards_frame = cards_frame.merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    card_results: dict[str, list[dict[str, object]]] = {
        "constant_train_rate": [],
        "legacy": [],
        "referee_enhanced": [],
    }
    for index in range(1, len(seasons)):
        train_seasons = seasons[:index]
        test_season = seasons[index]
        card_results["constant_train_rate"].append(
            evaluate_constant(
                cards_frame,
                "total_yellows_over_3_5",
                train_seasons,
                test_season,
            )
        )
        card_results["legacy"].append(
            evaluate_cards(
                cards_frame,
                LEGACY_CARD_FEATURE_COLUMNS,
                train_seasons,
                test_season,
            )
        )
        card_results["referee_enhanced"].append(
            evaluate_cards(
                cards_frame,
                CARD_FEATURE_COLUMNS,
                train_seasons,
                test_season,
            )
        )

    results = {
        "seasons": seasons,
        "walk_forward_rule": "train on all seasons before the held-out season; no shuffling",
        "btts": {
            "variants": btts_results,
            "summary": {
                name: average_metrics(values) for name, values in btts_results.items()
            },
        },
        "cards": {
            "variants": card_results,
            "summary": {
                name: average_metrics(values) for name, values in card_results.items()
            },
        },
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
