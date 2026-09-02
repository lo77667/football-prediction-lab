"""Build and evaluate the referee-aware total-yellow-cards baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.cards import build_card_features
from football_prediction_lab.models.btts import temporal_split
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/2425_E0.csv")
    parser.add_argument("--output", default="reports/generated/cards_baseline_holdout.csv")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_path = root / args.input
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    matches = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    features = build_card_features(matches)
    split = temporal_split(features, train_fraction=0.7, validation_fraction=0.15)
    model = TotalYellowCardsBaseline().fit(split.train)
    holdout = pd.concat([split.validation, split.test], ignore_index=True)
    holdout = holdout.assign(
        probability_yes=model.predict_probability(holdout).to_numpy(),
    )
    summary = evaluate_binary(holdout["probability_yes"], holdout["total_yellows_over_3_5"])
    holdout.to_csv(output_path, index=False)
    print(f"rows={len(features)}")
    print(f"holdout_rows={len(holdout)}")
    print(f"cards_over_3_5_rate={features['total_yellows_over_3_5'].mean():.4f}")
    print(f"metrics={summary.as_dict()}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
