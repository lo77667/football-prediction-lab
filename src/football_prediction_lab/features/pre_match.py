"""Point-in-time pre-match feature generation."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

import pandas as pd

WINDOWS = (5, 10)
_BASE_FEATURES = (
    "avg_scored",
    "avg_conceded",
    "btts_rate",
    "points_avg",
    "shots_on_target_avg",
    "corners_avg",
    "clean_sheet_rate",
)
_ROLLING_COLUMNS = [
    f"{side}_{metric}_{window}"
    for side in ("home", "away")
    for window in WINDOWS
    for metric in _BASE_FEATURES
]
_DERIVED_COLUMNS = [
    f"{name}_{window}"
    for window in WINDOWS
    for name in (
        "home_attack_signal",
        "away_attack_signal",
        "expected_total_goals",
        "attack_product",
        "btts_rate_product",
    )
]
FEATURE_COLUMNS = _ROLLING_COLUMNS + _DERIVED_COLUMNS + [
    "home_matches_before",
    "away_matches_before",
    "league_btts_rate_before",
    "league_avg_goals_before",
]


def feature_columns_for_window(window: int) -> list[str]:
    """Return the expanded BTTS feature columns for exactly one rolling window."""

    windows = _normalize_windows(window)
    if len(windows) != 1:
        raise ValueError("feature_columns_for_window requires exactly one window")
    selected = windows[0]
    rolling = [
        f"{side}_{metric}_{selected}"
        for side in ("home", "away")
        for metric in _BASE_FEATURES
    ]
    derived = [
        f"{name}_{selected}"
        for name in (
            "home_attack_signal",
            "away_attack_signal",
            "expected_total_goals",
            "attack_product",
            "btts_rate_product",
        )
    ]
    return rolling + derived + [
        "home_matches_before",
        "away_matches_before",
        "league_btts_rate_before",
        "league_avg_goals_before",
    ]


HistoryEntry = tuple[float, float, float, float, float, float, float]


def build_pre_match_features(
    matches: pd.DataFrame,
    *,
    window: int | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Build rolling and derived features using only prior matches."""

    windows = _normalize_windows(window)
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
    history: dict[str, deque[HistoryEntry]] = defaultdict(lambda: deque(maxlen=max(windows)))
    total_matches = 0
    total_btts = 0
    total_goals = 0.0
    records: list[dict[str, object]] = []

    for row in ordered.itertuples(index=False):
        home_history = history[row.home_team]
        away_history = history[row.away_team]
        home_goals = float(row.home_goals)
        away_goals = float(row.away_goals)
        home_sot = _optional_value(row, "home_shots_on_target")
        away_sot = _optional_value(row, "away_shots_on_target")
        home_corners = _optional_value(row, "home_corners")
        away_corners = _optional_value(row, "away_corners")
        home_points = 3.0 if home_goals > away_goals else 1.0 if home_goals == away_goals else 0.0
        away_points = 3.0 if away_goals > home_goals else 1.0 if home_goals == away_goals else 0.0
        record: dict[str, object] = {
            "match_id": row.match_id,
            "kickoff_utc": row.kickoff_utc,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "btts": int(row.btts),
            "home_matches_before": len(home_history),
            "away_matches_before": len(away_history),
            "league_btts_rate_before": total_btts / total_matches if total_matches else 0.0,
            "league_avg_goals_before": total_goals / total_matches if total_matches else 0.0,
        }
        for current_window in windows:
            record.update(_summary(home_history, "home", current_window))
            record.update(_summary(away_history, "away", current_window))
            record.update(_derived(record, current_window))

        records.append(record)
        home_history.append(
            (
                home_goals,
                away_goals,
                float(row.btts),
                home_points,
                home_sot,
                home_corners,
                float(home_goals == 0),
            )
        )
        away_history.append(
            (
                away_goals,
                home_goals,
                float(row.btts),
                away_points,
                away_sot,
                away_corners,
                float(away_goals == 0),
            )
        )
        total_matches += 1
        total_btts += int(row.btts)
        total_goals += home_goals + away_goals

    return pd.DataFrame(records)


def _normalize_windows(window: int | tuple[int, ...] | None) -> tuple[int, ...]:
    if window is None:
        return WINDOWS
    windows = (window,) if isinstance(window, int) else tuple(window)
    if not windows or any(value < 1 for value in windows):
        raise ValueError("windows must contain positive integers")
    return tuple(dict.fromkeys(windows))


def _optional_value(row: object, field: str) -> float:
    value = getattr(row, field, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _derived(record: dict[str, object], window: int) -> dict[str, float]:
    home_attack = float(record[f"home_avg_scored_{window}"]) + float(
        record[f"away_avg_conceded_{window}"]
    )
    away_attack = float(record[f"away_avg_scored_{window}"]) + float(
        record[f"home_avg_conceded_{window}"]
    )
    return {
        f"home_attack_signal_{window}": home_attack,
        f"away_attack_signal_{window}": away_attack,
        f"expected_total_goals_{window}": home_attack + away_attack,
        f"attack_product_{window}": home_attack * away_attack,
        f"btts_rate_product_{window}": float(record[f"home_btts_rate_{window}"])
        * float(record[f"away_btts_rate_{window}"]),
    }


def _summary(
    history: Iterable[HistoryEntry], prefix: str, window: int
) -> dict[str, float]:
    values = list(history)[-window:]
    if not values:
        return {
            f"{prefix}_avg_scored_{window}": 0.0,
            f"{prefix}_avg_conceded_{window}": 0.0,
            f"{prefix}_btts_rate_{window}": 0.0,
            f"{prefix}_points_avg_{window}": 0.0,
            f"{prefix}_shots_on_target_avg_{window}": 0.0,
            f"{prefix}_corners_avg_{window}": 0.0,
            f"{prefix}_clean_sheet_rate_{window}": 0.0,
        }
    return {
        f"{prefix}_avg_scored_{window}": _mean(values, 0),
        f"{prefix}_avg_conceded_{window}": _mean(values, 1),
        f"{prefix}_btts_rate_{window}": _mean(values, 2),
        f"{prefix}_points_avg_{window}": _mean(values, 3),
        f"{prefix}_shots_on_target_avg_{window}": _mean(values, 4),
        f"{prefix}_corners_avg_{window}": _mean(values, 5),
        f"{prefix}_clean_sheet_rate_{window}": _mean(values, 6),
    }


def _mean(values: list[HistoryEntry], index: int) -> float:
    return sum(value[index] for value in values) / len(values)
