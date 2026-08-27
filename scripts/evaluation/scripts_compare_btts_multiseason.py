"""Compare legacy and expanded BTTS features without using the test set for selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football_prediction_lab.evaluation.metrics import (
    evaluate_binary,
    expected_calibration_error,
    reliability_table,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, temporal_split


def fit_predict(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    feature_columns: list[str],
) -> pd.Series:
    pipeline = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1_000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(train[feature_columns], train["btts"])
    return pd.Series(
        pipeline.predict_proba(evaluation[feature_columns])[:, 1],
        index=evaluation.index,
        name="probability_yes",
    )


def summarize(probability: pd.Series, actual: pd.Series) -> dict[str, object]:
    evaluation = evaluate_binary(probability, actual)
    reliability = reliability_table(probability, actual, bins=5).copy()
    reliability = reliability.dropna(subset=["mean_probability", "observed_rate"])
    reliability["bucket"] = reliability["bucket"].astype(str)
    return {
        "metrics": evaluation.as_dict(),
        "expected_calibration_error_10": expected_calibration_error(
            probability, actual, bins=10
        ),
        "reliability": reliability.to_dict(orient="records"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/btts_variant_multiseason.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    variants = {
        "legacy": LEGACY_FEATURE_COLUMNS,
        "expanded": FEATURE_COLUMNS,
    }
    results: dict[str, object] = {
        "dataset": {
            "rows": len(frame),
            "date_min": frame["kickoff_utc"].min().isoformat(),
            "date_max": frame["kickoff_utc"].max().isoformat(),
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
            "test_rows": len(split.test),
            "selection_rule": (
                "choose by validation Brier, then validation Log Loss; "
                "test is not used for selection"
            ),
        },
        "variants": {},
    }

    validation_scores: dict[str, tuple[float, float]] = {}
    for name, feature_columns in variants.items():
        validation_probability = fit_predict(split.train, split.validation, feature_columns)
        test_probability = fit_predict(
            pd.concat([split.train, split.validation], ignore_index=True),
            split.test,
            feature_columns,
        )
        validation_result = summarize(validation_probability, split.validation["btts"])
        test_result = summarize(test_probability, split.test["btts"])
        validation_metrics = validation_result["metrics"]
        validation_scores[name] = (
            float(validation_metrics["brier_score"]),
            float(validation_metrics["log_loss"]),
        )
        results["variants"][name] = {
            "feature_count": len(feature_columns),
            "validation": validation_result,
            "test": test_result,
        }

    if "season" in frame.columns:
        season_labels = frame["season"].astype(str)
        historical = frame[season_labels != "2425"].copy()
        final_season = frame[season_labels == "2425"].copy()
        if len(historical) and len(final_season):
            seasonal_results: dict[str, object] = {
                "train_rows": len(historical),
                "test_rows": len(final_season),
                "test_season": "2425",
                "variants": {},
            }
            for name, feature_columns in variants.items():
                probability = fit_predict(historical, final_season, feature_columns)
                seasonal_results["variants"][name] = summarize(
                    probability, final_season["btts"]
                )
            results["season_2425_holdout"] = seasonal_results

    selected = min(validation_scores, key=lambda name: validation_scores[name])
    results["validation_selected_variant"] = selected
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
