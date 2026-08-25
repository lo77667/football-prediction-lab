"""Validate a normalized season file before using it as a future holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    path = root / args.input
    frame = pd.read_csv(path, parse_dates=["kickoff_utc"])
    required = {
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
    }
    missing = sorted(required.difference(frame.columns))
    target_cards = (frame["home_yellows"] + frame["away_yellows"] > 3).astype(int)
    result = {
        "input": args.input,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(frame),
        "missing_required_columns": missing,
        "duplicate_match_ids": int(frame["match_id"].duplicated().sum()),
        "time_parse_failures": int(frame["kickoff_utc"].isna().sum()),
        "time_monotonic_in_input": bool(frame["kickoff_utc"].is_monotonic_increasing),
        "season_values": sorted(frame["season"].astype(str).unique()),
        "date_min": str(frame["kickoff_utc"].min()),
        "date_max": str(frame["kickoff_utc"].max()),
        "unique_home_teams": int(frame["home_team"].nunique()),
        "unique_away_teams": int(frame["away_team"].nunique()),
        "null_counts": {
            column: int(frame[column].isna().sum())
            for column in (
                "home_goals",
                "away_goals",
                "home_yellows",
                "away_yellows",
                "referee",
                "btts",
            )
        },
        "btts_rate": float(frame["btts"].mean()),
        "cards_over_3_5_rate": float(target_cards.mean()),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
