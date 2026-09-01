"""Download one public Football-Data.co.uk season for the first data check."""

from __future__ import annotations

import argparse
from pathlib import Path

from football_prediction_lab.data.football_data import download_csv, normalize_football_data_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2425")
    parser.add_argument("--competition", default="E0")
    parser.add_argument(
        "--competition-name", help="canonical competition name for normalized output"
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="explicitly allow the legacy public download",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    raw_path = root / "data" / "raw" / f"{args.season}_{args.competition}.csv"
    processed_path = root / "data" / "processed" / f"{args.season}_{args.competition}.csv"
    url = f"https://www.football-data.co.uk/mmz4281/{args.season}/{args.competition}.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)

    download_csv(url, raw_path, allow_network=args.allow_network)
    competition_names = {
        "E0": "English Premier League",
        "SP1": "Spanish La Liga",
        "D1": "German Bundesliga",
        "I1": "Italian Serie A",
        "F1": "French Ligue 1",
    }
    normalized = normalize_football_data_csv(
        raw_path,
        competition=args.competition_name
        or competition_names.get(args.competition, args.competition),
        season=args.season,
    )
    normalized.to_csv(processed_path, index=False)
    print(f"downloaded_rows={len(normalized)}")
    print(f"raw_path={raw_path}")
    print(f"processed_path={processed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
