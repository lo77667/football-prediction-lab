"""Compare card feature families on one fixed temporal split."""

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
from football_prediction_lab.models.btts import temporal_split
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def feature_variants() -> dict[str, list[str]]:
    team_context = [column for column in CARD_FEATURE_COLUMNS if not column.startswith("referee_")]
    return {
        "legacy": LEGACY_CARD_FEATURE_COLUMNS,
        "team_context": team_context,
        "referee_enhanced": CARD_FEATURE_COLUMNS,
    }


def evaluate_variant(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, object]:
    model = TotalYellowCardsBaseline(feature_columns=feature_columns).fit(train)
    return evaluate_binary(
        model.predict_probability(evaluation), evaluation["total_yellows_over_3_5"]
    ).as_dict()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--output", default="reports/generated/cards_ablation.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    frame = build_card_features(matches)
    split = temporal_split(frame)
    variants = feature_variants()
    validation = {
        name: evaluate_variant(split.train, split.validation, columns)
        for name, columns in variants.items()
    }
    selected = min(
        validation,
        key=lambda name: (
            validation[name]["brier_score"],
            validation[name]["log_loss"],
        ),
    )
    combined = pd.concat([split.train, split.validation], ignore_index=True)
    result = {
        "selection_rule": (
            "select one card feature family on validation Brier then Log Loss; "
            "evaluate only selected family on test"
        ),
        "feature_counts": {name: len(columns) for name, columns in variants.items()},
        "validation": validation,
        "selected_variant": selected,
        "test_selected_variant": {
            selected: evaluate_variant(combined, split.test, variants[selected])
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
