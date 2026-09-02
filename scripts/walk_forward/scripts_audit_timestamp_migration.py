"""Audit timestamp and identity migration between feature artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["kickoff_utc"])


def _identity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[["match_id", "kickoff_utc"]].copy()
    result["kickoff_utc"] = pd.to_datetime(
        result["kickoff_utc"], utc=True, errors="coerce", format="mixed"
    )
    return result.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)


def _time_summary(frame: pd.DataFrame) -> dict[str, object]:
    timestamps = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce", format="mixed")
    return {
        "rows": len(frame),
        "parse_failures": int(timestamps.isna().sum()),
        "timezone": str(timestamps.dt.tz),
        "midnight_rows": int(((timestamps.dt.hour == 0) & (timestamps.dt.minute == 0)).sum()),
        "min": None if timestamps.dropna().empty else str(timestamps.min()),
        "max": None if timestamps.dropna().empty else str(timestamps.max()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--old", required=True)
    parser.add_argument("--rebuilt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    input_frame = _read(root / args.input)
    old_frame = _read(root / args.old)
    rebuilt_frame = _read(root / args.rebuilt)
    input_identity = _identity(input_frame)
    rebuilt_identity = _identity(rebuilt_frame)
    old_identity = _identity(old_frame)
    merged_old = input_identity.merge(
        old_identity,
        on="match_id",
        how="outer",
        suffixes=("_input", "_old"),
        indicator=True,
    )
    merged_rebuilt = input_identity.merge(
        rebuilt_identity,
        on="match_id",
        how="outer",
        suffixes=("_input", "_rebuilt"),
        indicator=True,
    )
    old_time_mismatch = int(
        (
            (merged_old["_merge"] == "both")
            & (merged_old["kickoff_utc_input"] != merged_old["kickoff_utc_old"])
        ).sum()
    )
    rebuilt_time_mismatch = int(
        (
            (merged_rebuilt["_merge"] == "both")
            & (merged_rebuilt["kickoff_utc_input"] != merged_rebuilt["kickoff_utc_rebuilt"])
        ).sum()
    )
    result = {
        "input": _time_summary(input_frame),
        "old_features": _time_summary(old_frame),
        "rebuilt_features": _time_summary(rebuilt_frame),
        "old_missing_match_ids": int((merged_old["_merge"] == "left_only").sum()),
        "old_extra_match_ids": int((merged_old["_merge"] == "right_only").sum()),
        "old_timestamp_mismatches_by_match_id": old_time_mismatch,
        "rebuilt_missing_match_ids": int((merged_rebuilt["_merge"] == "left_only").sum()),
        "rebuilt_extra_match_ids": int((merged_rebuilt["_merge"] == "right_only").sum()),
        "rebuilt_timestamp_mismatches_by_match_id": rebuilt_time_mismatch,
        "rebuilt_sorted_identity_matches_input": input_identity.equals(rebuilt_identity),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
