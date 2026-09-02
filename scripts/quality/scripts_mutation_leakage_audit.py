"""Audit current-row leakage by mutating outcomes and comparing same-row features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.features.pre_match import (
    build_pre_match_features,
    feature_columns_for_window,
)


def audit_btts(
    frame: pd.DataFrame,
    indices: list[int],
    *,
    window: int | None = None,
) -> list[dict[str, object]]:
    original = build_pre_match_features(frame, window=window)
    feature_columns = (
        feature_columns_for_window(window)
        if window is not None
        else feature_columns_for_window(5) + feature_columns_for_window(10)[-19:]
    )
    results = []
    for index in indices:
        mutated = frame.copy()
        for column in ["home_goals", "away_goals", "btts", "home_shots_on_target", "away_corners"]:
            if column in mutated.columns:
                mutated.loc[index, column] = 0 if mutated.loc[index, column] else 3
        candidate = build_pre_match_features(mutated, window=window)
        match_id = frame.iloc[index]["match_id"]
        left = original.loc[original["match_id"] == match_id, feature_columns].iloc[0]
        right = candidate.loc[candidate["match_id"] == match_id, feature_columns].iloc[0]
        results.append({"match_id": match_id, "unchanged": bool(left.equals(right))})
    return results


def audit_cards(frame: pd.DataFrame, indices: list[int]) -> list[dict[str, object]]:
    original = build_card_features(frame)
    results = []
    for index in indices:
        mutated = frame.copy()
        for column in [
            "home_yellows",
            "away_yellows",
            "home_fouls",
            "away_corners",
            "referee",
        ]:
            if column in mutated.columns and column != "referee":
                mutated.loc[index, column] = 0 if mutated.loc[index, column] else 9
        candidate = build_card_features(mutated)
        match_id = frame.iloc[index]["match_id"]
        left = original.loc[original["match_id"] == match_id, CARD_FEATURE_COLUMNS].iloc[0]
        right = candidate.loc[candidate["match_id"] == match_id, CARD_FEATURE_COLUMNS].iloc[0]
        results.append({"match_id": match_id, "unchanged": bool(left.equals(right))})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--features-input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--output", default="reports/generated/mutation_leakage_audit.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    indices = sorted({0, len(matches) // 2, len(matches) - 1})
    btts_results = {
        str(window): audit_btts(matches, indices, window=window) for window in (3, 5, 10)
    }
    cards_results = audit_cards(matches, indices)
    result = {
        "rule": "mutating the current match must not change its pre-match feature vector",
        "btts": btts_results,
        "cards": cards_results,
        "all_btts_unchanged": all(
            row["unchanged"] for rows in btts_results.values() for row in rows
        ),
        "all_cards_unchanged": all(row["unchanged"] for row in cards_results),
        "features_input_reference": args.features_input,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
