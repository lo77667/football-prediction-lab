"""Verify the normalized initial dataset without modifying it."""

from pathlib import Path

import pandas as pd


def main() -> int:
    path = Path(__file__).resolve().parent / "data" / "processed" / "2425_E0.csv"
    frame = pd.read_csv(path)
    print(f"columns={list(frame.columns)}")
    print(f"rows={len(frame)}")
    print(f"date_min={frame['kickoff_utc'].min()}")
    print(f"date_max={frame['kickoff_utc'].max()}")
    print(f"btts_rate={frame['btts'].mean():.4f}")
    print(f"duplicate_match_ids={int(frame['match_id'].duplicated().sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
