"""Normalize a manually supplied Football-Data season file."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from football_prediction_lab.data.football_data import normalize_football_data_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--competition", default="English Premier League")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    input_path = root / args.input
    output_path = root / args.output
    normalized = normalize_football_data_csv(
        input_path,
        competition=args.competition,
        season=args.season,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False)
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    print(f"rows={len(normalized)}")
    print(f"season={args.season}")
    print(f"input_sha256={digest}")
    print(f"date_min={normalized['kickoff_utc'].min()}")
    print(f"date_max={normalized['kickoff_utc'].max()}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
