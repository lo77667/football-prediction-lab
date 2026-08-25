"""Profile a processed dataset before model evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.data_quality import profile_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="reports/generated/data_quality_report.json")
    parser.add_argument("--target", action="append", default=[])
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    required = ["match_id", "kickoff_utc", "home_team", "away_team", *args.target]
    report = profile_dataset(
        frame,
        required_columns=required,
        target_columns=args.target,
    )
    report["input"] = args.input
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
