"""Point-in-time features for the total-yellow-cards market."""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

CARD_FEATURE_COLUMNS = [
    "home_avg_yellows",
    "away_avg_yellows",
    "home_avg_reds",
    "away_avg_reds",
    "home_card_matches_before",
    "away_card_matches_before",
]


def build_card_features(matches: pd.DataFrame, *, window: int = 5) -> pd.DataFrame:
    """Build rolling team card features without using the current match's cards."""

    required = {
        "match_id",
        "kickoff_utc",
        "home_team",
        "away_team",
        "home_yellows",
        "away_yellows",
        "home_reds",
        "away_reds",
    }
    missing = required.difference(matches.columns)
    if missing:
        raise ValueError(f"Missing card columns: {sorted(missing)}")
    if window < 1:
        raise ValueError("window must be at least 1")

    ordered = matches.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    history: dict[str, deque[tuple[float, float]]] = defaultdict(
        lambda: deque(maxlen=window)
    )
    rows: list[dict[str, object]] = []

    for row in ordered.itertuples(index=False):
        home_history = history[row.home_team]
        away_history = history[row.away_team]
        home_yellows = _number_or_zero(row.home_yellows)
        away_yellows = _number_or_zero(row.away_yellows)
        home_reds = _number_or_zero(row.home_reds)
        away_reds = _number_or_zero(row.away_reds)
        rows.append(
            {
                "match_id": row.match_id,
                "kickoff_utc": row.kickoff_utc,
                "home_team": row.home_team,
                "away_team": row.away_team,
                "home_yellows": home_yellows,
                "away_yellows": away_yellows,
                "total_yellows": home_yellows + away_yellows,
                "total_yellows_over_3_5": int(home_yellows + away_yellows > 3),
                **_summary(home_history, "home"),
                **_summary(away_history, "away"),
            }
        )
        history[row.home_team].append((home_yellows, home_reds))
        history[row.away_team].append((away_yellows, away_reds))

    return pd.DataFrame(rows)


def _number_or_zero(value: object) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _summary(history: deque[tuple[float, float]], prefix: str) -> dict[str, float | int]:
    if not history:
        return {
            f"{prefix}_avg_yellows": 0.0,
            f"{prefix}_avg_reds": 0.0,
            f"{prefix}_card_matches_before": 0,
        }
    return {
        f"{prefix}_avg_yellows": sum(item[0] for item in history) / len(history),
        f"{prefix}_avg_reds": sum(item[1] for item in history) / len(history),
        f"{prefix}_card_matches_before": len(history),
    }
