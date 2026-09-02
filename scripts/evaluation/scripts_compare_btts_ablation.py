"""Compare BTTS feature families on one fixed temporal split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import (
    LEGACY_FEATURE_COLUMNS,
    BttsLogisticBaseline,
    temporal_split,
)


def feature_variants() -> dict[str, list[str]]:
    rolling_only = [
        column for column in FEATURE_COLUMNS if column.endswith("_5") or column.endswith("_10")
    ]
    rolling_plus_context = [
        column
        for column in FEATURE_COLUMNS
        if column not in {"league_btts_rate_before", "league_avg_goals_before"}
        and not column.startswith("home_attack_signal_")
        and not column.startswith("away_attack_signal_")
        and not column.startswith("expected_total_goals_")
        and not column.startswith("attack_product_")
        and not column.startswith("btts_rate_product_")
    ]
    return {
        "legacy": LEGACY_FEATURE_COLUMNS,
        "rolling_only": rolling_only,
        "rolling_plus_context": rolling_plus_context,
        "full_expanded": FEATURE_COLUMNS,
    }


def evaluate_variant(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, object]:
    model = BttsLogisticBaseline(feature_columns=feature_columns).fit(train)
    return evaluate_binary(model.predict_probability(evaluation), evaluation["btts"]).as_dict()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/btts_ablation.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
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
    test = {selected: evaluate_variant(combined, split.test, variants[selected])}
    result = {
        "selection_rule": (
            "select one feature family on validation Brier then Log Loss; "
            "evaluate only selected family on test"
        ),
        "feature_counts": {name: len(columns) for name, columns in variants.items()},
        "validation": validation,
        "selected_variant": selected,
        "test_selected_variant": test,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
