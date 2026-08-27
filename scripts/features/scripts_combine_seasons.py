"""Combine normalized league seasons for reproducible multi-season experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition", default="E0")
    parser.add_argument("--output", default="data/processed/epl_1819_2425.csv")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_paths = sorted(
        path
        for path in (root / "data" / "processed").glob(f"*_{args.competition}.csv")
        if path.name != Path(args.output).name
    )
    if not input_paths:
        raise FileNotFoundError("no normalized season files found")
    frames = [pd.read_csv(path, parse_dates=["kickoff_utc"]) for path in input_paths]
    combined = pd.concat(frames, ignore_index=True)
    duplicate_match_ids = int(combined.duplicated("match_id").sum())
    combined = (
        combined.drop_duplicates("match_id", keep="first")
        .sort_values(["kickoff_utc", "match_id"])
        .reset_index(drop=True)
    )
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)
    print(f"source_files={len(input_paths)}")
    print(f"source_rows={sum(len(frame) for frame in frames)}")
    print(f"duplicate_match_ids={duplicate_match_ids}")
    print(f"combined_rows={len(combined)}")
    print(f"date_min={combined['kickoff_utc'].min()}")
    print(f"date_max={combined['kickoff_utc'].max()}")
    print(f"btts_rate={combined['btts'].mean():.4f}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
