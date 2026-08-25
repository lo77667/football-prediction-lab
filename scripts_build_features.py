"""Build point-in-time features for the initial normalized dataset."""

from pathlib import Path

import pandas as pd

from football_prediction_lab.features.pre_match import FEATURE_COLUMNS, build_pre_match_features


def main() -> int:
    root = Path(__file__).resolve().parent
    input_path = root / "data" / "processed" / "2425_E0.csv"
    output_path = root / "data" / "processed" / "2425_E0_features.csv"
    frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    features = build_pre_match_features(frame, window=5)
    features.to_csv(output_path, index=False)
    print(f"rows={len(features)}")
    print(f"feature_count={len(FEATURE_COLUMNS)}")
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
