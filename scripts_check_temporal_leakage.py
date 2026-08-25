"""Measure same-day temporal leakage in the current feature pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> int:
    root = Path(__file__).resolve().parent
    raw = pd.read_csv(root / "data" / "raw" / "2425_E0.csv")
    raw["actual_kickoff"] = pd.to_datetime(
        raw["Date"].astype(str) + " " + raw["Time"].astype(str),
        format="%d/%m/%Y %H:%M",
        errors="coerce",
        utc=True,
    )
    processed = pd.read_csv(
        root / "data" / "processed" / "2425_E0.csv", parse_dates=["kickoff_utc"]
    )
    processed["date"] = processed["kickoff_utc"].dt.date
    raw_keys = raw[["Date", "HomeTeam", "AwayTeam", "actual_kickoff"]].copy()
    merged = processed.merge(
        raw_keys,
        left_on=["home_team", "away_team"],
        right_on=["HomeTeam", "AwayTeam"],
        how="left",
    )
    merged = merged.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    duplicate_date_rows = int(merged["date"].duplicated(keep=False).sum())
    duplicate_date_groups = int(merged["date"].value_counts().gt(1).sum())
    leaked_rows: set[str] = set()
    leaked_team_events = 0
    for team_column in ("home_team", "away_team"):
        for team, group in merged.groupby(team_column, sort=False):
            prior_actual_times: list[pd.Timestamp] = []
            for row in group.itertuples(index=False):
                actual = row.actual_kickoff
                if pd.notna(actual):
                    leaked = sum(previous >= actual for previous in prior_actual_times)
                    if leaked:
                        leaked_rows.add(row.match_id)
                        leaked_team_events += leaked
                    prior_actual_times.append(actual)
    result = {
        "rows": len(merged),
        "duplicate_date_groups": duplicate_date_groups,
        "rows_on_dates_with_multiple_matches": duplicate_date_rows,
        "match_rows_with_same_day_leakage": len(leaked_rows),
        "leaked_team_history_events": leaked_team_events,
        "time_parse_failures": int(merged["actual_kickoff"].isna().sum()),
        "pipeline_kickoff_has_time": bool(
            (merged["kickoff_utc"].dt.hour != 0).any()
            or (merged["kickoff_utc"].dt.minute != 0).any()
        ),
    }
    output = root / "reports" / "generated" / "temporal_leakage_diagnosis.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
