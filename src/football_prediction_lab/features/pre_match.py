"""Point-in-time pre-match feature generation with additional contextual features.

Added features:
- fatigue_index: matches played in prior 14 days per team (home_fatigue_14d, away_fatigue_14d)
- match_importance: integer flag (0=normal,1=high_importance) based on current season standings (top/bottom thresholds)

Enhanced _optional_value to use team-historical median or league running average as fallbacks
and emit warnings if fallbacks are used extensively (>20% of rows).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Deque, Dict, Iterable as IterableTyp, Optional, Tuple

import logging
import statistics

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
# New contextual features: fatigue index for prior 14 days and match_importance flag
FEATURE_COLUMNS = _ROLLING_COLUMNS + _DERIVED_COLUMNS + [
    "home_matches_before",
    "away_matches_before",
    "league_btts_rate_before",
    "league_avg_goals_before",
    "home_fatigue_14d",
    "away_fatigue_14d",
    "match_importance",
]
PRE_MATCH_FEATURE_COLUMNS = tuple(FEATURE_COLUMNS)


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
        "home_fatigue_14d",
        "away_fatigue_14d",
        "match_importance",
    ]


# HistoryEntry keeps the same numeric layout as before
HistoryEntry = Tuple[float, float, float, float, float, float, float]

# Map optional stat field names to their index in HistoryEntry for team-historical median fallback
_STAT_INDEX: Dict[str, int] = {
    "shots_on_target": 4,
    "corners": 5,
}


def build_pre_match_features(
    matches: pd.DataFrame,
    *,
    window: int | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Build rolling, derived and contextual features using only prior matches.

    This function strictly uses only information available prior to each match (no future leakage).
    If 'season' is present in the input frame, match_importance will be computed using running
    season standings (points). Otherwise match_importance defaults to 0.
    """

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

    normalized = matches.copy()
    normalized["kickoff_utc"] = pd.to_datetime(
        normalized["kickoff_utc"], utc=True, errors="raise", format="mixed"
    )
    ordered = normalized.sort_values(
        ["kickoff_utc", "match_id"]
    ).reset_index(drop=True)

    # Rolling numeric history (same layout as before)
    history: Dict[str, Deque[HistoryEntry]] = defaultdict(lambda: deque(maxlen=max(windows)))
    # Keep per-team recent kickoff timestamps to compute fatigue in a 14-day window
    history_dates: Dict[str, Deque[pd.Timestamp]] = defaultdict(lambda: deque(maxlen=256))

    # Running league-level aggregates for fallback averages
    total_matches = 0
    total_btts = 0
    total_goals = 0.0
    total_shots_on_target = 0.0
    total_shots_count = 0
    total_corners = 0.0
    total_corners_count = 0

    # Running season points to compute provisional standings (if season column exists)
    season_points: Dict[object, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    records: list[Dict[str, object]] = []
    fallback_counts: Dict[str, int] = defaultdict(int)

    for row in ordered.itertuples(index=False):
        home_history = history[row.home_team]
        away_history = history[row.away_team]
        home_goals = float(row.home_goals)
        away_goals = float(row.away_goals)

        # Shots / corners: use optional value with team-history / league-average fallbacks
        home_sot = _optional_value(
            row,
            "home_shots_on_target",
            team_history=home_history,
            stat_name="shots_on_target",
            fallback_counters=fallback_counts,
            league_running_avg=(total_shots_on_target, total_shots_count),
        )
        away_sot = _optional_value(
            row,
            "away_shots_on_target",
            team_history=away_history,
            stat_name="shots_on_target",
            fallback_counters=fallback_counts,
            league_running_avg=(total_shots_on_target, total_shots_count),
        )
        home_corners = _optional_value(
            row,
            "home_corners",
            team_history=home_history,
            stat_name="corners",
            fallback_counters=fallback_counts,
            league_running_avg=(total_corners, total_corners_count),
        )
        away_corners = _optional_value(
            row,
            "away_corners",
            team_history=away_history,
            stat_name="corners",
            fallback_counters=fallback_counts,
            league_running_avg=(total_corners, total_corners_count),
        )

        home_points = 3.0 if home_goals > away_goals else 1.0 if home_goals == away_goals else 0.0
        away_points = 3.0 if away_goals > home_goals else 1.0 if home_goals == away_goals else 0.0

        # Compute fatigue: matches for team in prior 14 days
        kickoff = pd.to_datetime(row.kickoff_utc)
        home_fatigue = _count_recent_matches(history_dates[row.home_team], kickoff, days=14)
        away_fatigue = _count_recent_matches(history_dates[row.away_team], kickoff, days=14)

        # Compute provisional match importance using running season standings if available
        match_importance_flag = 0
        if "season" in ordered.columns:
            current_season = getattr(row, "season", None)
            if current_season is not None:
                # get current standings for the season
                standings = season_points[current_season]
                # if we have at least some standings built, compute position percentiles
                if standings:
                    # build sorted list of teams by points (descending)
                    teams_sorted = sorted(standings.items(), key=lambda kv: -kv[1])
                    team_rank = {team: rank + 1 for rank, (team, _) in enumerate(teams_sorted)}
                    num_teams = len(teams_sorted)
                    # if either team is in top 3 or bottom 3 -> high importance
                    home_rank = team_rank.get(row.home_team)
                    away_rank = team_rank.get(row.away_team)
                    threshold = 3
                    if (
                        (home_rank is not None and (home_rank <= threshold or home_rank > num_teams - threshold))
                        or (away_rank is not None and (away_rank <= threshold or away_rank > num_teams - threshold))
                    ):
                        match_importance_flag = 1

        record: Dict[str, object] = {
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
            "home_fatigue_14d": float(home_fatigue),
            "away_fatigue_14d": float(away_fatigue),
            "match_importance": int(match_importance_flag),
        }

        for current_window in windows:
            record.update(_summary(home_history, "home", current_window))
            record.update(_summary(away_history, "away", current_window))
            record.update(_derived(record, current_window))

        records.append(record)

        # append histories AFTER computing features to avoid leakage
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

        # update date histories used for fatigue calculation
        history_dates[row.home_team].append(kickoff)
        history_dates[row.away_team].append(kickoff)

        # update running league aggregates for fallbacks
        if not pd.isna(home_sot):
            total_shots_on_target += float(home_sot)
            total_shots_count += 1
        if not pd.isna(away_sot):
            total_shots_on_target += float(away_sot)
            total_shots_count += 1
        if not pd.isna(home_corners):
            total_corners += float(home_corners)
            total_corners_count += 1
        if not pd.isna(away_corners):
            total_corners += float(away_corners)
            total_corners_count += 1

        total_matches += 1
        total_btts += int(row.btts)
        total_goals += home_goals + away_goals

        # update season_points for standings (only after computing importance to avoid leakage)
        if "season" in ordered.columns:
            season = getattr(row, "season", None)
            if season is not None:
                season_points[season][row.home_team] += home_points
                season_points[season][row.away_team] += away_points

    frame = pd.DataFrame(records)

    # Emit warnings if fallback values were used extensively (>20% of rows)
    total_rows = len(frame)
    logger = logging.getLogger(__name__)
    for field, count in fallback_counts.items():
        if total_rows and count / total_rows > 0.2:
            logger.warning(
                "Fallback values used for %s in %.1f%% of rows (%d/%d). "
                "Using league/team fallbacks can affect auditability.",
                field,
                100.0 * count / total_rows,
                count,
                total_rows,
            )

    return frame


def _normalize_windows(window: int | tuple[int, ...] | None) -> tuple[int, ...]:
    if window is None:
        return WINDOWS
    windows = (window,) if isinstance(window, int) else tuple(window)
    if not windows or any(value < 1 for value in windows):
        raise ValueError("windows must contain positive integers")
    return tuple(dict.fromkeys(windows))


def _optional_value(
    row: object,
    field: str,
    *,
    team_history: Optional[Deque[HistoryEntry]] = None,
    stat_name: Optional[str] = None,
    fallback_counters: Optional[Dict[str, int]] = None,
    league_running_avg: Optional[Tuple[float, int]] = None,
) -> float:
    """Return a numeric stat from the row or use smart fallbacks.

    Fallback priority:
    1. If field exists and not NaN -> use value
    2. If team_history provided and non-empty -> use team-historical median for the stat
    3. If league_running_avg provided -> use running league average
    4. Otherwise return 0.0

    The function increments fallback_counters[stat_name] when a fallback is used.
    """

    # try direct value
    value = getattr(row, field, None)
    if value is not None and not pd.isna(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            # fall through to fallback
            pass

    # team-historical median (if available)
    if stat_name and team_history and len(team_history) > 0:
        stat_index = _STAT_INDEX.get(stat_name)
        if stat_index is not None:
            try:
                values = [entry[stat_index] for entry in team_history if not pd.isna(entry[stat_index])]
                if values:
                    median = float(statistics.median(values))
                    if fallback_counters is not None:
                        fallback_counters[stat_name] = fallback_counters.get(stat_name, 0) + 1
                    return median
            except Exception:
                # if median computation fails, continue to league average
                pass

    # league running average fallback
    if league_running_avg is not None:
        total, count = league_running_avg
        if count and not pd.isna(total):
            try:
                avg = float(total) / int(count)
                if fallback_counters is not None and stat_name:
                    fallback_counters[stat_name] = fallback_counters.get(stat_name, 0) + 1
                return avg
            except Exception:
                pass

    # ultimate default
    if fallback_counters is not None and stat_name:
        fallback_counters[stat_name] = fallback_counters.get(stat_name, 0) + 1
    return 0.0


def _count_recent_matches(dates: Deque[pd.Timestamp], kickoff: pd.Timestamp, *, days: int = 14) -> int:
    """Count prior matches in dates deque that are strictly before kickoff and within the lookback window."""

    cutoff = kickoff - pd.Timedelta(days=days)
    count = 0
    for d in reversed(dates):
        if d >= kickoff:
            # future or same-time entries shouldn't exist, but skip to be safe
            continue
        if d >= cutoff:
            count += 1
        else:
            # dates are appended in time order; once outside window we can stop
            break
    return count


def _derived(record: Dict[str, object], window: int) -> Dict[str, float]:
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
    history: IterableTyp[HistoryEntry], prefix: str, window: int
) -> Dict[str, float]:
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
