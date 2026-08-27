"""Measure temporal ordering risks in the current feature pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1819_2425.csv")
    parser.add_argument(
        "--output", default="reports/generated/temporal_leakage_diagnosis.json"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    processed = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    processed = processed.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    processed["date"] = processed["kickoff_utc"].dt.date
    duplicate_date_rows = int(processed["date"].duplicated(keep=False).sum())
    duplicate_date_groups = int(processed["date"].value_counts().gt(1).sum())
    leaked_rows: set[str] = set()
    leaked_team_events = 0
    for team_column in ("home_team", "away_team"):
        for _, group in processed.groupby(team_column, sort=False):
            prior_actual_times: list[pd.Timestamp] = []
            for row in group.itertuples(index=False):
                leaked = sum(previous > row.kickoff_utc for previous in prior_actual_times)
                if leaked:
                    leaked_rows.add(row.match_id)
                    leaked_team_events += leaked
                prior_actual_times.append(row.kickoff_utc)
    result = {
        "rows": len(processed),
        "duplicate_date_groups": duplicate_date_groups,
        "rows_on_dates_with_multiple_matches": duplicate_date_rows,
        "match_rows_with_same_day_leakage": len(leaked_rows),
        "leaked_team_history_events": leaked_team_events,
        "time_parse_failures": int(processed["kickoff_utc"].isna().sum()),
        "pipeline_kickoff_has_time": bool(
            (processed["kickoff_utc"].dt.hour != 0).any()
            or (processed["kickoff_utc"].dt.minute != 0).any()
        ),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
