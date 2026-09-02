"""Apply the calibration release gate to a saved walk-forward report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.learning.retraining import decide_calibration_retraining


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="reports/generated/walk_forward_calibrated_btts_ten_seasons.json",
    )
    parser.add_argument("--output", default="reports/generated/calibration_release_decision.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    report = json.loads((root / args.input).read_text(encoding="utf-8"))
    decision = decide_calibration_retraining(
        report["summary"]["base"],
        report["summary"]["calibrated"],
    )
    folds = report["folds"]
    fold_comparison = {
        "brier_wins": sum(
            float(fold["calibrated"]["brier_score"]) < float(fold["base"]["brier_score"])
            for fold in folds
        ),
        "log_loss_wins": sum(
            float(fold["calibrated"]["log_loss"]) < float(fold["base"]["log_loss"])
            for fold in folds
        ),
        "joint_probability_metric_wins": sum(
            float(fold["calibrated"]["brier_score"]) < float(fold["base"]["brier_score"])
            and float(fold["calibrated"]["log_loss"]) < float(fold["base"]["log_loss"])
            for fold in folds
        ),
        "ece_wins": sum(
            float(fold["calibrated_ece_10"]) <= float(fold["base_ece_10"]) for fold in folds
        ),
        "total_folds": len(folds),
    }
    result = {
        "input": args.input,
        "accepted": decision.accepted,
        "reason": decision.reason,
        "baseline": report["summary"]["base"],
        "candidate": report["summary"]["calibrated"],
        "fold_comparison": fold_comparison,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0 if decision.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
