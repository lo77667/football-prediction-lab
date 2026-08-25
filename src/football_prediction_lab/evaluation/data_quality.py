"""Auditable data-quality checks for point-in-time football datasets."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

DEFAULT_NON_NEGATIVE_COLUMNS = (
    "home_goals",
    "away_goals",
    "home_yellows",
    "away_yellows",
    "home_reds",
    "away_reds",
    "total_yellows",
)


def profile_dataset(
    frame: pd.DataFrame,
    *,
    required_columns: Sequence[str],
    id_column: str = "match_id",
    time_column: str = "kickoff_utc",
    target_columns: Sequence[str] = (),
    group_column: str | None = "season",
    team_columns: Sequence[str] = ("home_team", "away_team"),
    non_negative_columns: Sequence[str] = DEFAULT_NON_NEGATIVE_COLUMNS,
) -> dict[str, object]:
    """Return auditable quality checks without imputing or changing the frame."""

    missing_columns = [column for column in required_columns if column not in frame.columns]
    duplicate_ids = 0
    if id_column in frame.columns:
        duplicate_ids = int(frame[id_column].duplicated().sum())

    time_parse_failures = 0
    timezone_aware = False
    monotonic = True
    ordered_by_time_and_id = True
    if time_column in frame.columns:
        raw_timestamps = frame[time_column]
        parsed = pd.to_datetime(raw_timestamps, utc=True, errors="coerce", format="mixed")
        time_parse_failures = int(parsed.isna().sum())
        timezone_aware = _all_timezone_aware(raw_timestamps, parsed)
        valid = parsed.notna()
        monotonic = bool(parsed[valid].is_monotonic_increasing)
        if id_column in frame.columns:
            order_frame = pd.DataFrame(
                {time_column: parsed, id_column: frame[id_column].astype("string")}
            ).loc[valid]
            expected = order_frame.sort_values([time_column, id_column]).index
            ordered_by_time_and_id = bool(order_frame.index.equals(expected))

    blank_team_rows = 0
    present_team_columns = [column for column in team_columns if column in frame.columns]
    if present_team_columns:
        blank_team_rows = int(
            frame[present_team_columns]
            .astype("string")
            .apply(lambda values: values.isna() | values.str.strip().eq(""))
            .any(axis=1)
            .sum()
        )

    negative_value_rows: dict[str, int] = {}
    for column in non_negative_columns:
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            negative_value_rows[column] = int((values < 0).sum())

    duplicate_match_context_rows = 0
    context_columns = [*team_columns, time_column]
    if all(column in frame.columns for column in context_columns):
        normalized_time = pd.to_datetime(
            frame[time_column], utc=True, errors="coerce", format="mixed"
        )
        context = frame[[*team_columns]].copy()
        context[time_column] = normalized_time
        duplicate_match_context_rows = int(context.duplicated().sum())

    target_rates: dict[str, object] = {}
    for column in target_columns:
        if column not in frame.columns:
            target_rates[column] = {"missing": True}
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        target_rates[column] = {
            "missing": False,
            "null_rows": int(series.isna().sum()),
            "mean": None if series.dropna().empty else float(series.mean()),
        }

    groups: list[dict[str, object]] = []
    if group_column and group_column in frame.columns:
        for group, subset in frame.groupby(group_column, sort=True, dropna=False):
            record: dict[str, object] = {"group": str(group), "rows": len(subset)}
            for column in target_columns:
                if column in subset.columns:
                    record[f"{column}_rate"] = float(pd.to_numeric(subset[column]).mean())
            groups.append(record)

    return {
        "rows": len(frame),
        "columns": len(frame.columns),
        "missing_required_columns": missing_columns,
        "duplicate_id_rows": duplicate_ids,
        "duplicate_match_context_rows": duplicate_match_context_rows,
        "blank_team_rows": blank_team_rows,
        "negative_value_rows": negative_value_rows,
        "time_parse_failures": time_parse_failures,
        "timezone_aware": timezone_aware,
        "time_monotonic_in_input": monotonic,
        "ordered_by_time_and_id": ordered_by_time_and_id,
        "target_rates": target_rates,
        "groups": groups,
    }


def _all_timezone_aware(values: pd.Series, parsed_utc: pd.Series) -> bool:
    """Return true only when every non-null parseable value carries an offset."""

    for value, parsed in zip(values, parsed_utc, strict=True):
        if pd.isna(value):
            continue
        if pd.isna(parsed):
            return False
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return False
    return True
