"""Download one public Football-Data.co.uk season for the first data check."""

from __future__ import annotations

import argparse
from pathlib import Path

from football_prediction_lab.data.football_data import download_csv, normalize_football_data_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2425")
    parser.add_argument("--competition", default="E0")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[0]
    raw_path = root / "data" / "raw" / f"{args.season}_{args.competition}.csv"
    processed_path = root / "data" / "processed" / f"{args.season}_{args.competition}.csv"
    url = f"https://www.football-data.co.uk/mmz4281/{args.season}/{args.competition}.csv"

    download_csv(url, raw_path)
    normalized = normalize_football_data_csv(
        raw_path,
        competition="English Premier League",
        season=args.season,
    )
    normalized.to_csv(processed_path, index=False)
    print(f"downloaded_rows={len(normalized)}")
    print(f"raw_path={raw_path}")
    print(f"processed_path={processed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
