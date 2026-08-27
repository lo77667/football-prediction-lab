"""Analyze current out-of-sample errors without changing any model or ledger."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.models.btts import temporal_split


def summarize(frame: pd.DataFrame, probability: str, actual: str) -> dict[str, object]:
    values = frame[probability].astype(float)
    labels = frame[actual].astype(int)
    decisions = (values >= 0.5).astype(int)
    actual_rate = float(labels.mean())
    constant_brier = actual_rate * (1 - actual_rate)
    by_band = (
        frame.assign(
            band=pd.cut(
                values,
                bins=[-0.001, 0.4, 0.6, 1.001],
                labels=["low", "medium", "high"],
                include_lowest=True,
            ),
            correct=(decisions == labels).astype(int),
        )
        .groupby("band", observed=False)
        .agg(
            rows=(actual, "size"),
            accuracy=("correct", "mean"),
            actual_rate=(actual, "mean"),
            mean_probability=(probability, "mean"),
        )
        .reset_index()
    )
    return {
        "rows": len(frame),
        "actual_rate": actual_rate,
        "accuracy_at_0_5": float((decisions == labels).mean()),
        "always_yes_accuracy": actual_rate,
        "always_no_accuracy": float(1 - actual_rate),
        "brier_model": float(np.mean((values - labels) ** 2)),
        "brier_constant_actual_rate": constant_brier,
        "brier_delta_vs_constant": float(np.mean((values - labels) ** 2) - constant_brier),
        "mean_probability": float(values.mean()),
        "std_probability": float(values.std(ddof=0)),
        "min_probability": float(values.min()),
        "max_probability": float(values.max()),
        "near_half_fraction": float(((values >= 0.45) & (values <= 0.55)).mean()),
        "high_confidence_rows": int(((values < 0.4) | (values > 0.6)).sum()),
        "false_positive": int(((decisions == 1) & (labels == 0)).sum()),
        "false_negative": int(((decisions == 0) & (labels == 1)).sum()),
        "by_confidence_band": by_band.to_dict(orient="records"),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    report_dir = root / "reports" / "generated"
    btts = pd.read_csv(report_dir / "btts_errors.csv")
    cards = pd.read_csv(report_dir / "cards_baseline_holdout.csv")
    source_matches = pd.read_csv(root / "data" / "processed" / "2425_E0.csv")
    features = pd.read_csv(
        root / "data" / "processed" / "2425_E0_features.csv",
        parse_dates=["kickoff_utc"],
    )
    split = temporal_split(features, train_fraction=0.7, validation_fraction=0.15)
    summary = {
        "btts": summarize(btts, "probability_yes", "actual_yes"),
        "cards_over_3_5": summarize(cards, "probability_yes", "total_yellows_over_3_5"),
        "card_data_missing": {
            column: int(source_matches[column].isna().sum())
            for column in ["home_yellows", "away_yellows", "home_reds", "away_reds"]
        },
        "btts_temporal_rates": {
            "train": float(split.train["btts"].mean()),
            "validation": float(split.validation["btts"].mean()),
            "test": float(split.test["btts"].mean()),
        },
        "card_feature_variance": {
            column: float(cards[column].astype(float).var(ddof=0))
            for column in [
                "home_avg_yellows",
                "away_avg_yellows",
                "home_avg_reds",
                "away_avg_reds",
            ]
        },
    }
    output = report_dir / "current_error_analysis.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
