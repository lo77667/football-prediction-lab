"""Dataset quality and temporal distribution diagnostics."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def profile_dataset(
    frame: pd.DataFrame,
    *,
    required_columns: Sequence[str],
    id_column: str = "match_id",
    time_column: str = "kickoff_utc",
    target_columns: Sequence[str] = (),
    group_column: str | None = "season",
) -> dict[str, object]:
    """Return auditable quality checks without imputing or changing the frame."""

    missing_columns = [column for column in required_columns if column not in frame.columns]
    duplicate_ids = 0
    if id_column in frame.columns:
        duplicate_ids = int(frame[id_column].duplicated().sum())
    time_parse_failures = 0
    monotonic = True
    if time_column in frame.columns:
        timestamps = pd.to_datetime(
            frame[time_column], utc=True, errors="coerce", format="mixed"
        )
        time_parse_failures = int(timestamps.isna().sum())
        monotonic = bool(timestamps.dropna().is_monotonic_increasing)
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
        "time_parse_failures": time_parse_failures,
        "time_monotonic_in_input": monotonic,
        "target_rates": target_rates,
        "groups": groups,
    }
