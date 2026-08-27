"""Build point-in-time features for a normalized dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import (
    assert_identity_columns_match,
    build_manifest,
    sha256_file,
    write_manifest,
)
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS, build_pre_match_features

PASSTHROUGH_COLUMNS = (
    "competition",
    "season",
    "home_yellows",
    "away_yellows",
    "home_reds",
    "away_reds",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_fouls",
    "away_fouls",
    "referee",
    "total_yellows",
    "source",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/processed/2425_E0.csv",
        help="normalized CSV path relative to the repository root",
    )
    parser.add_argument(
        "--output",
        default="data/processed/2425_E0_features.csv",
        help="feature CSV path relative to the repository root",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_path = root / args.input
    output_path = root / args.output
    frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    features = build_pre_match_features(frame)
    assert_identity_columns_match(frame, features)
    passthrough = [
        column
        for column in PASSTHROUGH_COLUMNS
        if column in frame.columns and column not in features.columns
    ]
    if passthrough:
        features = features.merge(
            frame[["match_id", *passthrough]],
            on="match_id",
            how="left",
            validate="one_to_one",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest = build_manifest(
        input_path=str(input_path),
        input_sha256=sha256_file(input_path),
        output_path=str(output_path),
        rows_before=len(frame),
        rows_after=len(features),
        frame=features,
        feature_version="pre-match-rolling-v0.3",
    )
    write_manifest(manifest, manifest_path)
    print(f"rows={len(features)}")
    print(f"feature_count={len(FEATURE_COLUMNS)}")
    print(f"passthrough_count={len(passthrough)}")
    print(f"output_path={output_path}")
    print(f"manifest_path={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
