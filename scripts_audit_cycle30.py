"""Audit cycle-30 rebuilds against old artifacts and normalized inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.data_quality import profile_dataset

SEASONS = ("1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526")


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["kickoff_utc"])


def _identity(frame: pd.DataFrame) -> pd.DataFrame:
    identity = frame[["match_id", "kickoff_utc"]].copy()
    identity["kickoff_utc"] = pd.to_datetime(
        identity["kickoff_utc"], utc=True, errors="coerce", format="mixed"
    )
    return identity.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)


def _same_day(frame: pd.DataFrame) -> dict[str, int]:
    timestamps = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce")
    counts = timestamps.dt.date.value_counts()
    busy = counts[counts > 1]
    return {
        "days_with_multiple_matches": int(len(busy)),
        "rows_on_multi_match_days": int(busy.sum()),
        "max_matches_on_one_day": int(counts.max()) if not counts.empty else 0,
    }


def _identity_summary(input_frame: pd.DataFrame, artifact: pd.DataFrame) -> dict[str, object]:
    left = _identity(input_frame)
    right = _identity(artifact)
    merged = left.merge(
        right,
        on="match_id",
        how="outer",
        suffixes=("_input", "_artifact"),
        indicator=True,
    )
    both = merged["_merge"] == "both"
    return {
        "rows_input": len(input_frame),
        "rows_artifact": len(artifact),
        "missing_match_ids": int((merged["_merge"] == "left_only").sum()),
        "extra_match_ids": int((merged["_merge"] == "right_only").sum()),
        "timestamp_mismatches_by_match_id": int(
            (both & (merged["kickoff_utc_input"] != merged["kickoff_utc_artifact"])).sum()
        ),
        "sorted_identity_matches": left.equals(right),
    }


def _order_change(old: pd.DataFrame, rebuilt: pd.DataFrame) -> dict[str, int]:
    old_order = list(old["match_id"].astype(str))
    new_order = list(rebuilt["match_id"].astype(str))
    old_position = {match_id: index for index, match_id in enumerate(old_order)}
    comparable = [match_id for match_id in new_order if match_id in old_position]
    changed = sum(
        old_position[match_id] != index
        for index, match_id in enumerate(comparable)
    )
    return {
        "old_rows": len(old_order),
        "rebuilt_rows": len(new_order),
        "comparable_match_ids": len(comparable),
        "rows_with_changed_relative_position": int(changed),
    }


def _season_record(root: Path, season: str) -> dict[str, object]:
    source = _read(root / f"data/processed/{season}_E0.csv")
    source = source.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    old_path = root / f"data/processed/{season}_E0_features.csv"
    old_btts = _read(old_path) if old_path.exists() else None
    new_btts = _read(root / f"data/rebuilt/cycle30/{season}_E0_btts_features.csv")
    new_cards = _read(root / f"data/rebuilt/cycle30/{season}_E0_cards_features.csv")
    source_quality = profile_dataset(
        source,
        required_columns=("match_id", "kickoff_utc", "home_team", "away_team"),
        target_columns=("btts",),
    )
    new_btts_quality = profile_dataset(
        new_btts,
        required_columns=("match_id", "kickoff_utc"),
        target_columns=("btts",),
    )
    new_cards_quality = profile_dataset(
        new_cards,
        required_columns=("match_id", "kickoff_utc"),
        target_columns=("total_yellows_over_3_5",),
    )
    labels_unchanged = {
        "btts": source["btts"].astype(int).equals(new_btts["btts"].astype(int)),
        "cards": (
            (
                pd.to_numeric(source["home_yellows"], errors="raise")
                + pd.to_numeric(source["away_yellows"], errors="raise")
                > 3
            ).astype(int).equals(new_cards["total_yellows_over_3_5"].astype(int))
        ),
    }
    return {
        "season": season,
        "source_quality": source_quality,
        "old_btts_available": old_btts is not None,
        "old_btts_identity": (
            None if old_btts is None else _identity_summary(source, old_btts)
        ),
        "rebuilt_btts_identity": _identity_summary(source, new_btts),
        "rebuilt_cards_identity": _identity_summary(source, new_cards),
        "old_btts_time": (
            None
            if old_btts is None
            else profile_dataset(old_btts, required_columns=("match_id", "kickoff_utc"))
        ),
        "rebuilt_btts_quality": new_btts_quality,
        "rebuilt_cards_quality": new_cards_quality,
        "labels_unchanged": labels_unchanged,
        "same_day_source": _same_day(source),
        "same_day_old_btts": None if old_btts is None else _same_day(old_btts),
        "same_day_rebuilt_btts": _same_day(new_btts),
        "order_change_old_to_rebuilt": (
            None if old_btts is None else _order_change(old_btts, new_btts)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/migration_30/cycle30_audit.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    records = [_season_record(root, season) for season in SEASONS]
    result = {
        "protocol": "Migration-only rebuild; 2526 remains a frozen holdout.",
        "seasons": records,
        "all_labels_unchanged": all(
            all(record["labels_unchanged"].values()) for record in records
        ),
        "all_rebuilt_btts_identity_matches": all(
            record["rebuilt_btts_identity"]["sorted_identity_matches"]
            for record in records
        ),
        "all_rebuilt_cards_identity_matches": all(
            record["rebuilt_cards_identity"]["sorted_identity_matches"]
            for record in records
        ),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
