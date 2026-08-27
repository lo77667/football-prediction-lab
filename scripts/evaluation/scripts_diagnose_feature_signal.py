"""Diagnose feature signal and temporal distribution shift."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS
from football_prediction_lab.models.btts import temporal_split


def correlations(frame: pd.DataFrame, features: list[str], target: str) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for feature in features:
        if frame[feature].nunique(dropna=True) < 2 or frame[target].nunique(dropna=True) < 2:
            values[feature] = None
            continue
        correlation = frame[feature].corr(frame[target])
        values[feature] = None if pd.isna(correlation) else float(correlation)
    return values


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    processed = root / "data" / "processed"
    btts = pd.read_csv(processed / "2425_E0_features.csv", parse_dates=["kickoff_utc"])
    btts_split = temporal_split(btts, train_fraction=0.7, validation_fraction=0.15)
    cards = pd.read_csv(root / "reports" / "generated" / "cards_baseline_holdout.csv")
    source_matches = pd.read_csv(processed / "2425_E0.csv", parse_dates=["kickoff_utc"])
    card_features = build_card_features(source_matches, window=5)
    card_split = temporal_split(card_features, train_fraction=0.7, validation_fraction=0.15)

    result = {
        "btts": {
            "train": {
                "target_rate": float(btts_split.train["btts"].mean()),
                "feature_std": {
                    feature: float(btts_split.train[feature].std(ddof=0))
                    for feature in FEATURE_COLUMNS
                },
                "correlation": correlations(btts_split.train, FEATURE_COLUMNS, "btts"),
            },
            "validation": {
                "target_rate": float(btts_split.validation["btts"].mean()),
                "correlation": correlations(
                    btts_split.validation, FEATURE_COLUMNS, "btts"
                ),
            },
            "test": {
                "target_rate": float(btts_split.test["btts"].mean()),
                "correlation": correlations(btts_split.test, FEATURE_COLUMNS, "btts"),
            },
        },
        "cards": {
            "holdout_target_rate": float(cards["total_yellows_over_3_5"].mean()),
            "temporal_rates": {
                "train": float(card_split.train["total_yellows_over_3_5"].mean()),
                "validation": float(card_split.validation["total_yellows_over_3_5"].mean()),
                "test": float(card_split.test["total_yellows_over_3_5"].mean()),
            },
            "feature_std": {
                feature: float(cards[feature].std(ddof=0)) for feature in CARD_FEATURE_COLUMNS
            },
            "correlation": correlations(
                cards, CARD_FEATURE_COLUMNS, "total_yellows_over_3_5"
            ),
        },
    }
    output = root / "reports" / "generated" / "feature_signal_diagnosis.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
