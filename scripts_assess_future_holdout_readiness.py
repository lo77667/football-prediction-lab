"""Check whether a genuinely future holdout is available without fabricating data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--future-season", required=True)
    parser.add_argument("--historical-through", default="2425")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    frame = pd.read_csv(root / args.input, usecols=["season"])
    observed = sorted(frame["season"].astype(str).unique())
    requested = str(args.future_season)
    is_future = requested in observed and requested > str(args.historical_through)
    result = {
        "requested_future_season": requested,
        "latest_observed_season": observed[-1],
        "observed_seasons": observed,
        "ready": is_future,
        "decision": (
            "future holdout is present in the supplied file and may be evaluated"
            if is_future
            else (
                "defer: no genuinely future season is available; do not fabricate "
                "or reuse observed data"
            )
        ),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
