"""Compare BTTS weighting choices on the same future holdout."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import temporal_split


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, class_weight: str | None) -> pd.Series:
    pipeline = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1_000,
                    class_weight=class_weight,
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(train[FEATURE_COLUMNS], train["btts"])
    return pd.Series(pipeline.predict_proba(test[FEATURE_COLUMNS])[:, 1], index=test.index)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(
        root / "data" / "processed" / "2425_E0_features.csv",
        parse_dates=["kickoff_utc"],
    )
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    results: dict[str, dict[str, float | int]] = {}
    for name, class_weight in [("balanced", "balanced"), ("unweighted", None)]:
        probability = fit_predict(split.train, split.test, class_weight)
        evaluation = evaluate_binary(probability, split.test["btts"])
        results[name] = evaluation.as_dict()
    train_rate = float(split.train["btts"].mean())
    constant = evaluate_binary([train_rate] * len(split.test), split.test["btts"])
    results["constant_train_rate"] = constant.as_dict()
    output = root / "reports" / "generated" / "btts_variant_comparison.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, sort_keys=True))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
