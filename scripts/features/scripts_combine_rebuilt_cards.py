"""Combine cycle-30 per-season card artifacts into one local dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import build_manifest, sha256_file, write_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/rebuilt/cycle30")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    input_dir = root / args.input_dir
    paths = sorted(input_dir.glob("*_E0_cards_features.csv"))
    if not paths:
        raise FileNotFoundError("no rebuilt card files found")
    frames = [pd.read_csv(path, parse_dates=["kickoff_utc"]) for path in paths]
    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["kickoff_utc", "match_id"])
        .reset_index(drop=True)
    )
    if combined["match_id"].duplicated().any():
        raise ValueError("rebuilt cards contain duplicate match_id")
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    manifest = build_manifest(
        input_path=str(input_dir),
        input_sha256=sha256_file(paths[0]),
        output_path=str(output),
        rows_before=sum(len(frame) for frame in frames),
        rows_after=len(combined),
        frame=combined,
        feature_version="pre-match-cards-v0.4-combined",
    )
    write_manifest(manifest, output.with_suffix(output.suffix + ".manifest.json"))
    print(f"source_files={len(paths)}")
    print(f"source_rows={sum(len(frame) for frame in frames)}")
    print(f"combined_rows={len(combined)}")
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
