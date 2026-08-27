"""Rebuild pre-match artifacts without overwriting historical outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import (
    assert_identity_columns_match,
    build_manifest,
    sha256_file,
    write_manifest,
)
from football_prediction_lab.evaluation.data_quality import profile_dataset
from football_prediction_lab.features.cards import build_card_features
from football_prediction_lab.features.pre_match import build_pre_match_features

TARGET_COLUMNS = ("btts", "total_yellows_over_3_5")
REQUIRED_COLUMNS = (
    "match_id",
    "kickoff_utc",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_yellows",
    "away_yellows",
)


def _target_series(frame: pd.DataFrame) -> pd.Series:
    return (
        pd.to_numeric(frame["home_yellows"], errors="raise")
        + pd.to_numeric(frame["away_yellows"], errors="raise")
        > 3
    ).astype(int)


def _write_artifact(
    frame: pd.DataFrame,
    output_path: Path,
    input_path: Path,
    feature_version: str,
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    manifest = build_manifest(
        input_path=str(input_path),
        input_sha256=sha256_file(input_path),
        output_path=str(output_path),
        rows_before=len(frame),
        rows_after=len(frame),
        frame=frame,
        feature_version=feature_version,
    )
    write_manifest(
        manifest,
        output_path.with_suffix(output_path.suffix + ".manifest.json"),
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="data/rebuilt")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    input_path = root / args.input
    output_dir = root / args.output_dir
    source = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    missing = sorted(set(REQUIRED_COLUMNS).difference(source.columns))
    if missing:
        raise ValueError(f"Missing cycle 30 columns: {missing}")

    source = source.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    btts = build_pre_match_features(source)
    cards = build_card_features(source)
    assert_identity_columns_match(source, btts)
    assert_identity_columns_match(source, cards)

    expected_cards = _target_series(source)
    if "btts" in source.columns and not source["btts"].astype(int).equals(btts["btts"].astype(int)):
        raise ValueError("BTTS target changed during feature rebuild")
    if not expected_cards.equals(cards["total_yellows_over_3_5"].astype(int)):
        raise ValueError("Cards target changed during feature rebuild")

    stem = input_path.stem
    btts_path = output_dir / f"{stem}_btts_features.csv"
    cards_path = output_dir / f"{stem}_cards_features.csv"
    btts_manifest = _write_artifact(btts, btts_path, input_path, "pre-match-btts-v0.4")
    cards_manifest = _write_artifact(cards, cards_path, input_path, "pre-match-cards-v0.4")
    source_quality = profile_dataset(
        source,
        required_columns=REQUIRED_COLUMNS,
        target_columns=TARGET_COLUMNS,
    )
    btts_quality = profile_dataset(
        btts,
        required_columns=("match_id", "kickoff_utc"),
        target_columns=("btts",),
    )
    cards_quality = profile_dataset(
        cards,
        required_columns=("match_id", "kickoff_utc"),
        target_columns=("total_yellows_over_3_5",),
    )
    result = {
        "input_path": args.input,
        "input_sha256": sha256_file(input_path),
        "rows_input": len(source),
        "rows_btts": len(btts),
        "rows_cards": len(cards),
        "source_quality": source_quality,
        "btts_quality": btts_quality,
        "cards_quality": cards_quality,
        "target_labels_unchanged": True,
        "btts_manifest": btts_manifest,
        "cards_manifest": cards_manifest,
    }
    report_path = output_dir / f"{stem}_cycle30_rebuild.json"
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
