"""Select regularization and class weighting on validation only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.cards import build_card_features
from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split
from football_prediction_lab.models.cards import TotalYellowCardsBaseline

CANDIDATE_C_VALUES = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
CANDIDATE_WEIGHTS = (None, "balanced")


def tune_btts(frame: pd.DataFrame) -> dict[str, object]:
    split = temporal_split(frame)
    candidates = []
    for c_value in CANDIDATE_C_VALUES:
        for class_weight in CANDIDATE_WEIGHTS:
            model = BttsLogisticBaseline(
                c_value=c_value,
                class_weight=class_weight,
            ).fit(split.train)
            probability = model.predict_probability(split.validation)
            metrics = evaluate_binary(probability, split.validation["btts"]).as_dict()
            candidates.append(
                {
                    "c_value": c_value,
                    "class_weight": class_weight,
                    "validation": metrics,
                }
            )
    selected = min(
        candidates,
        key=lambda item: (
            item["validation"]["brier_score"],
            item["validation"]["log_loss"],
        ),
    )
    train = pd.concat([split.train, split.validation], ignore_index=True)
    final_model = BttsLogisticBaseline(
        c_value=selected["c_value"],
        class_weight=selected["class_weight"],
    ).fit(train)
    test_probability = final_model.predict_probability(split.test)
    return {
        "selected": selected,
        "test": evaluate_binary(test_probability, split.test["btts"]).as_dict(),
        "candidates": candidates,
    }


def tune_cards(frame: pd.DataFrame) -> dict[str, object]:
    split = temporal_split(frame)
    candidates = []
    for c_value in CANDIDATE_C_VALUES:
        for class_weight in CANDIDATE_WEIGHTS:
            model = TotalYellowCardsBaseline(
                c_value=c_value,
                class_weight=class_weight,
            ).fit(split.train)
            probability = model.predict_probability(split.validation)
            metrics = evaluate_binary(
                probability, split.validation["total_yellows_over_3_5"]
            ).as_dict()
            candidates.append(
                {
                    "c_value": c_value,
                    "class_weight": class_weight,
                    "validation": metrics,
                }
            )
    selected = min(
        candidates,
        key=lambda item: (
            item["validation"]["brier_score"],
            item["validation"]["log_loss"],
        ),
    )
    train = pd.concat([split.train, split.validation], ignore_index=True)
    final_model = TotalYellowCardsBaseline(
        c_value=selected["c_value"],
        class_weight=selected["class_weight"],
    ).fit(train)
    test_probability = final_model.predict_probability(split.test)
    return {
        "selected": selected,
        "test": evaluate_binary(
            test_probability, split.test["total_yellows_over_3_5"]
        ).as_dict(),
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425_features.csv")
    parser.add_argument("--cards-input", default="data/processed/epl_1819_2425.csv")
    parser.add_argument("--output", default="reports/generated/validation_tuning_results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    btts = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    matches = pd.read_csv(root / args.cards_input, parse_dates=["kickoff_utc"])
    cards = build_card_features(matches)
    cards = cards.merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    results = {
        "selection_policy": (
            "minimize validation Brier, then validation Log Loss; "
            "test is evaluated once after selection"
        ),
        "candidate_c_values": CANDIDATE_C_VALUES,
        "candidate_class_weights": CANDIDATE_WEIGHTS,
        "btts": tune_btts(btts),
        "cards": tune_cards(cards),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
