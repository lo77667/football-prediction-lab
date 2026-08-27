"""Normalize a manually supplied Football-Data season file."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.football_data import normalize_football_data_csv
from football_prediction_lab.data.provenance import (
    build_manifest,
    sha256_file,
    write_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--competition", default="English Premier League")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_path = root / args.input
    output_path = root / args.output
    rows_before = len(pd.read_csv(input_path))
    normalized = normalize_football_data_csv(
        input_path,
        competition=args.competition,
        season=args.season,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False)
    digest = sha256_file(input_path)
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest = build_manifest(
        input_path=str(input_path),
        input_sha256=digest,
        output_path=str(output_path),
        rows_before=rows_before,
        rows_after=len(normalized),
        frame=normalized,
        feature_version="normalized-match-v0.3",
    )
    write_manifest(manifest, manifest_path)
    print(f"rows={len(normalized)}")
    print(f"season={args.season}")
    print(f"input_sha256={digest}")
    print(f"date_min={normalized['kickoff_utc'].min()}")
    print(f"date_max={normalized['kickoff_utc'].max()}")
    print(f"output_path={output_path}")
    print(f"manifest_path={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
