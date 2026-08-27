"""Train and evaluate BTTS models with ordered holdout data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from football_prediction_lab.models.btts import (
    LEGACY_FEATURE_COLUMNS,
    BttsLogisticBaseline,
    temporal_split,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/2425_E0_features.csv")
    parser.add_argument("--output", default="reports/generated/btts_baseline_holdout.csv")
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_path = root / args.input
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    feature_columns = LEGACY_FEATURE_COLUMNS if args.legacy else None
    model = BttsLogisticBaseline(feature_columns=feature_columns).fit(split.train)
    holdout = pd.concat([split.validation, split.test], ignore_index=True)
    holdout = holdout.assign(
        probability_yes=model.predict_probability(holdout).to_numpy(),
    )
    holdout["decision"] = (holdout["probability_yes"] >= 0.5).astype("int8")
    holdout["correct_decision"] = (holdout["decision"] == holdout["btts"]).astype("int8")
    holdout.to_csv(output_path, index=False)

    print(f"feature_set={'legacy' if args.legacy else 'expanded'}")
    print(f"train_rows={len(split.train)}")
    print(f"validation_rows={len(split.validation)}")
    print(f"test_rows={len(split.test)}")
    print(f"holdout_rows={len(holdout)}")
    print(f"holdout_accuracy={holdout['correct_decision'].mean():.4f}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
