"""Point-in-time features for the total-yellow-cards market."""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

CARD_WINDOWS = (5, 10)
_BASE_CARD_FEATURES = (
    "avg_yellows",
    "avg_reds",
    "avg_fouls",
    "avg_corners",
)
LEGACY_CARD_FEATURE_COLUMNS = [
    "home_avg_yellows",
    "away_avg_yellows",
    "home_avg_reds",
    "away_avg_reds",
    "home_card_matches_before",
    "away_card_matches_before",
]

CARD_FEATURE_COLUMNS = [
    f"{side}_{metric}_{window}"
    for side in ("home", "away")
    for window in CARD_WINDOWS
    for metric in _BASE_CARD_FEATURES
] + ["referee_avg_yellows_10", "home_card_matches_before", "away_card_matches_before"]

TeamCardEntry = tuple[float, float, float, float]
RefereeCardEntry = tuple[float, float]


def build_card_features(
    matches: pd.DataFrame,
    *,
    window: int | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Build rolling team and referee card features before each match."""

    windows = _normalize_windows(window)
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

    ordered = matches.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    history: dict[str, deque[TeamCardEntry]] = defaultdict(
        lambda: deque(maxlen=max(windows))
    )
    referee_history: dict[str, deque[RefereeCardEntry]] = defaultdict(
        lambda: deque(maxlen=10)
    )
    rows: list[dict[str, object]] = []

    for row in ordered.itertuples(index=False):
        home_history = history[row.home_team]
        away_history = history[row.away_team]
        referee = str(getattr(row, "referee", "unknown") or "unknown")
        referee_entries = referee_history[referee]
        home_yellows = _number_or_zero(row.home_yellows)
        away_yellows = _number_or_zero(row.away_yellows)
        home_reds = _number_or_zero(row.home_reds)
        away_reds = _number_or_zero(row.away_reds)
        record: dict[str, object] = {
            "match_id": row.match_id,
            "kickoff_utc": row.kickoff_utc,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "home_yellows": home_yellows,
            "away_yellows": away_yellows,
            "total_yellows": home_yellows + away_yellows,
            "total_yellows_over_3_5": int(home_yellows + away_yellows > 3),
            "home_card_matches_before": len(home_history),
            "away_card_matches_before": len(away_history),
            "referee_matches_before": len(referee_entries),
            "referee_avg_yellows_10": _mean_referee(referee_entries, 0),
        }
        for current_window in windows:
            record.update(_summary(home_history, "home", current_window))
            record.update(_summary(away_history, "away", current_window))
        record.update(
            {
                "home_avg_yellows": record["home_avg_yellows_5"],
                "away_avg_yellows": record["away_avg_yellows_5"],
                "home_avg_reds": record["home_avg_reds_5"],
                "away_avg_reds": record["away_avg_reds_5"],
            }
        )

        rows.append(record)
        home_fouls = _optional_value(row, "home_fouls")
        away_fouls = _optional_value(row, "away_fouls")
        home_corners = _optional_value(row, "home_corners")
        away_corners = _optional_value(row, "away_corners")
        history[row.home_team].append((home_yellows, home_reds, home_fouls, home_corners))
        history[row.away_team].append((away_yellows, away_reds, away_fouls, away_corners))
        referee_history[referee].append((home_yellows + away_yellows, home_reds + away_reds))

    return pd.DataFrame(rows)


def _normalize_windows(window: int | tuple[int, ...] | None) -> tuple[int, ...]:
    if window is None:
        return CARD_WINDOWS
    windows = (window,) if isinstance(window, int) else tuple(window)
    if not windows or any(value < 1 for value in windows):
        raise ValueError("windows must contain positive integers")
    return tuple(dict.fromkeys(windows))


def _number_or_zero(value: object) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _optional_value(row: object, field: str) -> float:
    value = getattr(row, field, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _summary(
    history: deque[TeamCardEntry], prefix: str, window: int
) -> dict[str, float]:
    values = list(history)[-window:]
    if not values:
        return {
            f"{prefix}_avg_yellows_{window}": 0.0,
            f"{prefix}_avg_reds_{window}": 0.0,
            f"{prefix}_avg_fouls_{window}": 0.0,
            f"{prefix}_avg_corners_{window}": 0.0,
        }
    return {
        f"{prefix}_avg_yellows_{window}": _mean(values, 0),
        f"{prefix}_avg_reds_{window}": _mean(values, 1),
        f"{prefix}_avg_fouls_{window}": _mean(values, 2),
        f"{prefix}_avg_corners_{window}": _mean(values, 3),
    }


def _mean(values: list[TeamCardEntry], index: int) -> float:
    return sum(value[index] for value in values) / len(values)


def _mean_referee(values: deque[RefereeCardEntry], index: int) -> float:
    if not values:
        return 0.0
    return sum(value[index] for value in values) / len(values)
