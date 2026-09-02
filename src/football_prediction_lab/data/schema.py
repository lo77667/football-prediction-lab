"""Shared data contracts for pre-match modeling and post-match auditing."""

from __future__ import annotations

from collections.abc import Sequence

TARGET_COLUMNS = (
    "btts",
    "total_yellows_over_3_5",
)

POST_MATCH_AUDIT_COLUMNS = (
    "FTHG",
    "FTAG",
    "FTR",
    "home_goals",
    "away_goals",
    "btts",
    "HY",
    "AY",
    "HR",
    "AR",
    "home_yellows",
    "away_yellows",
    "home_reds",
    "away_reds",
    "total_yellows",
    "total_yellows_over_3_5",
    "HS",
    "AS",
    "HST",
    "AST",
    "HC",
    "AC",
    "HF",
    "AF",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_fouls",
    "away_fouls",
)


def validate_pre_match_feature_columns(feature_columns: Sequence[str]) -> None:
    """Reject targets and post-match audit fields used as model features."""

    forbidden = sorted(set(feature_columns).intersection(POST_MATCH_AUDIT_COLUMNS))
    if forbidden:
        raise ValueError("Feature columns contain post-match fields: " + ", ".join(forbidden))
