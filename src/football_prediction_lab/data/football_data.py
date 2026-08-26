"""Download and normalize historical Football-Data.co.uk CSV files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

REQUIRED_SOURCE_COLUMNS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}


def download_csv(
    url: str, destination: Path, timeout: int = 30, *, allow_network: bool = False
) -> Path:
    """Download a CSV only when the caller explicitly opts into network access."""

    if not allow_network:
        raise RuntimeError("network download is disabled; pass allow_network=True explicitly")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "football-prediction-lab/0.1"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is configured by the project
        destination.write_bytes(response.read())
    return destination


def normalize_football_data_csv(
    csv_path: Path,
    *,
    competition: str,
    season: str,
    source: str = "football-data.co.uk",
) -> pd.DataFrame:
    """Normalize a Football-Data CSV while preserving rows with parseable outcomes."""

    frame = pd.read_csv(csv_path)
    missing = REQUIRED_SOURCE_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required source columns: {sorted(missing)}")

    raw_dates = frame["Date"].astype("string").str.strip()
    raw_times = (
        frame["Time"].astype("string").str.strip()
        if "Time" in frame.columns
        else pd.Series("", index=frame.index, dtype="string")
    )
    date_time = (raw_dates + " " + raw_times).str.strip()
    kickoff = pd.to_datetime(date_time, format="%d/%m/%Y %H:%M", errors="coerce", utc=True)
    missing_time = kickoff.isna()
    if missing_time.any():
        kickoff.loc[missing_time] = pd.to_datetime(
            date_time.loc[missing_time], format="%d/%m/%y %H:%M", errors="coerce", utc=True
        )
    missing_datetime = kickoff.isna()
    if missing_datetime.any():
        kickoff.loc[missing_datetime] = pd.to_datetime(
            raw_dates.loc[missing_datetime], format="%d/%m/%Y", errors="coerce", utc=True
        )
    missing_short_date = kickoff.isna()
    if missing_short_date.any():
        kickoff.loc[missing_short_date] = pd.to_datetime(
            raw_dates.loc[missing_short_date], format="%d/%m/%y", errors="coerce", utc=True
        )
    goals_home = pd.to_numeric(frame["FTHG"], errors="coerce")
    goals_away = pd.to_numeric(frame["FTAG"], errors="coerce")
    normalized = pd.DataFrame(
        {
            "kickoff_utc": kickoff,
            "competition": competition,
            "season": season,
            "home_team": frame["HomeTeam"].astype("string").str.strip(),
            "away_team": frame["AwayTeam"].astype("string").str.strip(),
            "home_goals": goals_home,
            "away_goals": goals_away,
            "home_yellows": _optional_numeric(frame, "HY"),
            "away_yellows": _optional_numeric(frame, "AY"),
            "home_reds": _optional_numeric(frame, "HR"),
            "away_reds": _optional_numeric(frame, "AR"),
            "home_shots": _optional_numeric(frame, "HS"),
            "away_shots": _optional_numeric(frame, "AS"),
            "home_shots_on_target": _optional_numeric(frame, "HST"),
            "away_shots_on_target": _optional_numeric(frame, "AST"),
            "home_corners": _optional_numeric(frame, "HC"),
            "away_corners": _optional_numeric(frame, "AC"),
            "home_fouls": _optional_numeric(frame, "HF"),
            "away_fouls": _optional_numeric(frame, "AF"),
            "referee": _optional_text(frame, "Referee"),
            "source": source,
        }
    )
    normalized = normalized.dropna(
        subset=["kickoff_utc", "home_team", "away_team", "home_goals", "away_goals"]
    ).copy()
    normalized["home_goals"] = normalized["home_goals"].astype(int)
    normalized["away_goals"] = normalized["away_goals"].astype(int)
    if (normalized[["home_goals", "away_goals"]] < 0).any().any():
        raise ValueError("Goals cannot be negative")
    for column in ("home_yellows", "away_yellows", "home_reds", "away_reds"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").astype("Int64")
    normalized["total_yellows"] = normalized["home_yellows"] + normalized["away_yellows"]

    normalized["match_id"] = normalized.apply(_match_id, axis=1)
    normalized["btts"] = ((normalized["home_goals"] > 0) & (normalized["away_goals"] > 0)).astype(
        "int8"
    )
    columns = [
        "match_id",
        "kickoff_utc",
        "competition",
        "season",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "home_yellows",
        "away_yellows",
        "home_reds",
        "away_reds",
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_corners",
        "away_corners",
        "home_fouls",
        "away_fouls",
        "referee",
        "total_yellows",
        "btts",
        "source",
    ]
    return normalized[columns].sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)


def _optional_text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("unknown", index=frame.index, dtype="string")
    values = frame[column].astype("string").str.strip()
    return values.fillna("unknown").replace("", "unknown")


def _optional_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="Int64")
    return pd.to_numeric(frame[column], errors="coerce")


def _match_id(row: pd.Series) -> str:
    value = "|".join(
        [
            row["kickoff_utc"].isoformat(),
            row["home_team"],
            row["away_team"],
            row["competition"],
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
