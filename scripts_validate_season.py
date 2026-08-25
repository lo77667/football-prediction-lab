"""Validate a normalized season file and emit auditable metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import sha256_file
from football_prediction_lab.evaluation.data_quality import profile_dataset

REQUIRED_COLUMNS = (
    "match_id",
    "kickoff_utc",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_yellows",
    "away_yellows",
    "referee",
    "btts",
)
TARGET_COLUMNS = ("btts", "total_yellows_over_3_5")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    path = root / args.input
    frame = pd.read_csv(path, parse_dates=["kickoff_utc"])
    quality = profile_dataset(
        frame,
        required_columns=REQUIRED_COLUMNS,
        target_columns=TARGET_COLUMNS,
    )
    result = {
        "input_path": args.input,
        "input_sha256": sha256_file(path),
        "rows_before": len(frame),
        "rows_after": len(frame),
        "feature_version": "normalized-match-v0.3",
        "season_values": sorted(frame["season"].astype(str).unique())
        if "season" in frame.columns
        else [],
        "quality": quality,
    }
    if "kickoff_utc" in frame.columns:
        parsed = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce")
        result["kickoff_utc_min"] = None if parsed.dropna().empty else str(parsed.min())
        result["kickoff_utc_max"] = None if parsed.dropna().empty else str(parsed.max())
    else:
        result["kickoff_utc_min"] = None
        result["kickoff_utc_max"] = None
    if "home_team" in frame.columns:
        result["unique_home_teams"] = int(frame["home_team"].nunique())
    if "away_team" in frame.columns:
        result["unique_away_teams"] = int(frame["away_team"].nunique())

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
