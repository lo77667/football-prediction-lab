"""Compare quantitative-only and quantitative-plus-qualitative BTTS models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary, reliability_table
from football_prediction_lab.features.hybrid import (
    HYBRID_FEATURE_COLUMNS,
    build_qualitative_features,
    merge_hybrid_features,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split
from football_prediction_lab.qualitative.io import load_events_jsonl


def summarize(probability: pd.Series, actual: pd.Series) -> dict[str, object]:
    evaluation = evaluate_binary(probability, actual)
    reliability = reliability_table(probability, actual, bins=5).dropna(
        subset=["mean_probability", "observed_rate"]
    )
    reliability["bucket"] = reliability["bucket"].astype(str)
    return {
        "metrics": evaluation.as_dict(),
        "reliability": reliability.to_dict(orient="records"),
    }


def evaluate_variant(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, object]:
    model = BttsLogisticBaseline(feature_columns=feature_columns).fit(train)
    probability = model.predict_probability(evaluation)
    return summarize(probability, evaluation["btts"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425_features.csv")
    parser.add_argument("--qualitative-events", required=True)
    parser.add_argument("--output", default="reports/generated/btts_hybrid_ablation.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    quantitative = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    events_path = root / args.qualitative_events
    events = load_events_jsonl(events_path)
    qualitative = build_qualitative_features(quantitative, events)
    frame = merge_hybrid_features(quantitative, qualitative)
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    hybrid_columns = [*FEATURE_COLUMNS, *HYBRID_FEATURE_COLUMNS]
    validation_train = split.train
    test_train = pd.concat([split.train, split.validation], ignore_index=True)
    results = {
        "dataset": {
            "rows": len(frame),
            "events": len(events),
            "events_with_match_ids": len({event.match_id for event in events}),
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
            "test_rows": len(split.test),
            "selection_rule": (
                "validation is for selection; test remains a final untouched evaluation"
            ),
        },
        "quantitative_only": {
            "feature_count": len(FEATURE_COLUMNS),
            "validation": evaluate_variant(validation_train, split.validation, FEATURE_COLUMNS),
            "test": evaluate_variant(test_train, split.test, FEATURE_COLUMNS),
        },
        "quantitative_plus_qualitative": {
            "feature_count": len(hybrid_columns),
            "validation": evaluate_variant(validation_train, split.validation, hybrid_columns),
            "test": evaluate_variant(test_train, split.test, hybrid_columns),
        },
    }
    results["validation_selected_variant"] = min(
        ("quantitative_only", "quantitative_plus_qualitative"),
        key=lambda name: (
            results[name]["validation"]["metrics"]["brier_score"],
            results[name]["validation"]["metrics"]["log_loss"],
        ),
    )
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
