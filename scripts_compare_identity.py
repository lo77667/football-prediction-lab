"""Compare identity and timestamps between two CSV artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import assert_identity_columns_match


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    input_frame = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    output_frame = pd.read_csv(root / args.output, parse_dates=["kickoff_utc"])
    assert_identity_columns_match(input_frame, output_frame)
    timestamps = pd.to_datetime(output_frame["kickoff_utc"], utc=True, errors="raise")
    result = {
        "input_path": args.input,
        "output_path": args.output,
        "input_rows": len(input_frame),
        "output_rows": len(output_frame),
        "identity_match": True,
        "output_timezone": str(timestamps.dt.tz),
        "output_time_parse_failures": int(timestamps.isna().sum()),
        "output_midnight_rows": int(
            ((timestamps.dt.hour == 0) & (timestamps.dt.minute == 0)).sum()
        ),
        "output_min": str(timestamps.min()),
        "output_max": str(timestamps.max()),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
