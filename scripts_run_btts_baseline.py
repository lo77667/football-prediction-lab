"""Train and evaluate a baseline BTTS model with an ordered holdout."""

from pathlib import Path

import pandas as pd

from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split


def main() -> int:
    root = Path(__file__).resolve().parent
    input_path = root / "data" / "processed" / "2425_E0_features.csv"
    report_dir = root / "reports" / "generated"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / "btts_baseline_holdout.csv"

    frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    model = BttsLogisticBaseline().fit(split.train)
    holdout = pd.concat([split.validation, split.test], ignore_index=True)
    holdout = holdout.assign(
        probability_yes=model.predict_probability(holdout).to_numpy(),
    )
    holdout["decision"] = (holdout["probability_yes"] >= 0.5).astype("int8")
    holdout["correct_decision"] = (holdout["decision"] == holdout["btts"]).astype("int8")
    holdout.to_csv(output_path, index=False)

    print(f"train_rows={len(split.train)}")
    print(f"validation_rows={len(split.validation)}")
    print(f"test_rows={len(split.test)}")
    print(f"holdout_rows={len(holdout)}")
    print(f"holdout_accuracy={holdout['correct_decision'].mean():.4f}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
