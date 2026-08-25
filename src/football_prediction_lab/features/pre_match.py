"""Point-in-time pre-match feature generation."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

import pandas as pd

FEATURE_COLUMNS = [
    "home_avg_scored",
    "home_avg_conceded",
    "home_btts_rate",
    "away_avg_scored",
    "away_avg_conceded",
    "away_btts_rate",
    "home_matches_before",
    "away_matches_before",
]


def build_pre_match_features(
    matches: pd.DataFrame,
    *,
    window: int = 5,
) -> pd.DataFrame:
    """Build rolling features using only matches earlier than each kickoff.

    Rows are processed chronologically. The current match is appended to team history
    only after its features are computed, so its own result cannot leak into features.
    """

    if window < 1:
        raise ValueError("window must be at least 1")
    required = {
        "match_id",
        "kickoff_utc",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "btts",
    }
    missing = required.difference(matches.columns)
    if missing:
        raise ValueError(f"Missing columns for feature generation: {sorted(missing)}")

    ordered = matches.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    history: dict[str, deque[tuple[int, int, int]]] = defaultdict(
        lambda: deque(maxlen=window)
    )
    records: list[dict[str, object]] = []

    for row in ordered.itertuples(index=False):
        home_history = history[row.home_team]
        away_history = history[row.away_team]
        record = {
            "match_id": row.match_id,
            "kickoff_utc": row.kickoff_utc,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "home_goals": int(row.home_goals),
            "away_goals": int(row.away_goals),
            "btts": int(row.btts),
        }
        record.update(_summary(home_history, "home"))
        record.update(_summary(away_history, "away"))
        records.append(record)

        history[row.home_team].append((int(row.home_goals), int(row.away_goals), int(row.btts)))
        history[row.away_team].append((int(row.away_goals), int(row.home_goals), int(row.btts)))

    result = pd.DataFrame(records)
    return result


def _summary(history: Iterable[tuple[int, int, int]], prefix: str) -> dict[str, float | int]:
    values = list(history)
    if not values:
        return {
            f"{prefix}_avg_scored": 0.0,
            f"{prefix}_avg_conceded": 0.0,
            f"{prefix}_btts_rate": 0.0,
            f"{prefix}_matches_before": 0,
        }
    scored = [item[0] for item in values]
    conceded = [item[1] for item in values]
    btts = [item[2] for item in values]
    return {
        f"{prefix}_avg_scored": sum(scored) / len(scored),
        f"{prefix}_avg_conceded": sum(conceded) / len(conceded),
        f"{prefix}_btts_rate": sum(btts) / len(btts),
        f"{prefix}_matches_before": len(values),
    }
