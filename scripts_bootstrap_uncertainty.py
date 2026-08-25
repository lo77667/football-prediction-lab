"""Compute bootstrap intervals for a saved probability ledger or holdout CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.uncertainty import bootstrap_metric_intervals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--probability-column", default="probability_yes")
    parser.add_argument("--target-column", required=True)
    parser.add_argument("--output", default="reports/generated/bootstrap_uncertainty.json")
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    frame = pd.read_csv(root / args.input)
    missing = {args.probability_column, args.target_column}.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    result = bootstrap_metric_intervals(
        frame[args.probability_column],
        frame[args.target_column],
        n_resamples=args.resamples,
        seed=args.seed,
    )
    result["input"] = args.input
    result["probability_column"] = args.probability_column
    result["target_column"] = args.target_column
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
