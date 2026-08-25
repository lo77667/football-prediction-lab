"""Cleaning and validation for normalized football match data."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

REQUIRED_COLUMNS = {
    "match_id",
    "kickoff_utc",
    "competition",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "btts",
    "source",
}


def clean_matches(
    frame: pd.DataFrame,
    *,
    team_aliases: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return a clean, sorted match frame and a deterministic cleaning report."""

    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing normalized columns: {sorted(missing)}")

    result = frame.copy()
    initial_rows = len(result)
    result["kickoff_utc"] = pd.to_datetime(result["kickoff_utc"], utc=True, errors="coerce")
    for column in ("home_goals", "away_goals", "btts"):
        result[column] = pd.to_numeric(result[column], errors="coerce")

    for column in ("home_team", "away_team", "competition", "season", "source"):
        result[column] = result[column].astype("string").str.strip()

    if team_aliases:
        result["home_team"] = result["home_team"].replace(team_aliases)
        result["away_team"] = result["away_team"].replace(team_aliases)

    invalid_mask = (
        result["kickoff_utc"].isna()
        | result["home_team"].isna()
        | result["away_team"].isna()
        | (result["home_team"] == "")
        | (result["away_team"] == "")
        | result[["home_goals", "away_goals", "btts"]].isna().any(axis=1)
        | (result[["home_goals", "away_goals"]] < 0).any(axis=1)
    )
    invalid_rows = int(invalid_mask.sum())
    result = result.loc[~invalid_mask].copy()

    result["home_goals"] = result["home_goals"].astype(int)
    result["away_goals"] = result["away_goals"].astype(int)
    result["btts"] = ((result["home_goals"] > 0) & (result["away_goals"] > 0)).astype("int8")

    duplicate_rows = int(result.duplicated(subset=["match_id"], keep="first").sum())
    result = result.drop_duplicates(subset=["match_id"], keep="first")
    result = result.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)

    report = {
        "initial_rows": initial_rows,
        "invalid_rows_removed": invalid_rows,
        "duplicate_rows_removed": duplicate_rows,
        "final_rows": len(result),
    }
    return result, report
