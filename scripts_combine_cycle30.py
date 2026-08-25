"""Combine cycle-30 per-season artifacts without overwriting old outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/rebuilt/cycle30")
    parser.add_argument("--kind", choices=("normalized", "btts", "cards"), required=True)
    parser.add_argument("--seasons", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    input_dir = root / args.input_dir
    suffix = {
        "normalized": "_E0.csv",
        "btts": "_E0_btts_features.csv",
        "cards": "_E0_cards_features.csv",
    }[args.kind]
    paths = [input_dir / f"{season}{suffix}" for season in args.seasons]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing cycle 30 artifacts: {missing}")
    frames = [pd.read_csv(path, parse_dates=["kickoff_utc"]) for path in paths]
    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["kickoff_utc", "match_id"])
        .reset_index(drop=True)
    )
    if combined["match_id"].duplicated().any():
        raise ValueError("cycle 30 aggregate contains duplicate match_id")
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    print(f"kind={args.kind}")
    print(f"source_files={len(paths)}")
    print(f"source_rows={sum(len(frame) for frame in frames)}")
    print(f"combined_rows={len(combined)}")
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
