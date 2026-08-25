"""Compare legacy and referee-enhanced card features on future-only splits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary, reliability_table
from football_prediction_lab.features.cards import (
    CARD_FEATURE_COLUMNS,
    LEGACY_CARD_FEATURE_COLUMNS,
    build_card_features,
)
from football_prediction_lab.models.btts import temporal_split
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


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
    features: pd.DataFrame,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, object]:
    model = TotalYellowCardsBaseline(feature_columns=feature_columns).fit(train)
    probability = model.predict_probability(evaluation)
    return summarize(probability, evaluation["total_yellows_over_3_5"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425.csv")
    parser.add_argument("--output", default="reports/generated/cards_variant_multiseason.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    features = build_card_features(matches)
    split = temporal_split(features, train_fraction=0.7, validation_fraction=0.15)
    variants = {
        "legacy": LEGACY_CARD_FEATURE_COLUMNS,
        "referee_enhanced": CARD_FEATURE_COLUMNS,
    }
    results: dict[str, object] = {
        "dataset": {
            "rows": len(features),
            "date_min": features["kickoff_utc"].min().isoformat(),
            "date_max": features["kickoff_utc"].max().isoformat(),
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
            "test_rows": len(split.test),
            "target_rate": float(features["total_yellows_over_3_5"].mean()),
            "selection_rule": (
                "validation is reported for research selection; "
                "the final test is not used to select features"
            ),
        },
        "variants": {},
    }
    validation_scores: dict[str, tuple[float, float]] = {}
    for name, feature_columns in variants.items():
        validation = evaluate_variant(features, split.train, split.validation, feature_columns)
        test_train = pd.concat([split.train, split.validation], ignore_index=True)
        test = evaluate_variant(features, test_train, split.test, feature_columns)
        results["variants"][name] = {
            "feature_count": len(feature_columns),
            "validation": validation,
            "test": test,
        }
        validation_metrics = validation["metrics"]
        validation_scores[name] = (
            float(validation_metrics["brier_score"]),
            float(validation_metrics["log_loss"]),
        )

    if "season" in matches.columns:
        labels = matches["season"].astype(str)
        historical_matches = matches[labels != "2425"].copy()
        final_matches = matches[labels == "2425"].copy()
        if len(historical_matches) and len(final_matches):
            historical_features = build_card_features(historical_matches)
            final_features = build_card_features(matches)
            final_features = final_features[
                final_features["match_id"].isin(final_matches["match_id"])
            ].copy()
            seasonal_results: dict[str, object] = {
                "train_rows": len(historical_features),
                "test_rows": len(final_features),
                "test_season": "2425",
                "variants": {},
            }
            for name, feature_columns in variants.items():
                seasonal_results["variants"][name] = evaluate_variant(
                    features,
                    historical_features,
                    final_features,
                    feature_columns,
                )
            results["season_2425_holdout"] = seasonal_results

    results["validation_selected_variant"] = min(
        validation_scores, key=lambda name: validation_scores[name]
    )
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
