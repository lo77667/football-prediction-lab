"""Explore training-history sensitivity on a fixed future holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from football_prediction_lab.evaluation.metrics import evaluate_binary
from football_prediction_lab.features.cards import (
    LEGACY_CARD_FEATURE_COLUMNS,
    build_card_features,
)
from football_prediction_lab.models.btts import BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def evaluate_btts(
    frame: pd.DataFrame,
    train_seasons: list[str],
    test_season: str,
) -> dict[str, object]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = BttsLogisticBaseline().fit(train)
    return evaluate_binary(model.predict_probability(test), test["btts"]).as_dict()


def evaluate_cards(
    frame: pd.DataFrame,
    train_seasons: list[str],
    test_season: str,
) -> dict[str, object]:
    train = frame[frame["season"].astype(str).isin(train_seasons)]
    test = frame[frame["season"].astype(str) == test_season]
    model = TotalYellowCardsBaseline(feature_columns=LEGACY_CARD_FEATURE_COLUMNS).fit(train)
    return evaluate_binary(
        model.predict_probability(test), test["total_yellows_over_3_5"]
    ).as_dict()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425_features.csv")
    parser.add_argument("--cards-input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--test-season", default="2425")
    parser.add_argument("--output", default="reports/generated/training_window_sensitivity.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    btts = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    matches = pd.read_csv(root / args.cards_input, parse_dates=["kickoff_utc"])
    cards = build_card_features(matches).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    seasons = sorted(btts["season"].astype(str).unique())
    prior = [season for season in seasons if season < args.test_season]
    windows = {"last_3": prior[-3:], "last_5": prior[-5:], "all_prior": prior}
    result = {
        "test_season": args.test_season,
        "rule": (
            "fixed future holdout; windows are reported for sensitivity, "
            "not selected on the holdout"
        ),
        "btts": {
            name: evaluate_btts(btts, train, args.test_season)
            for name, train in windows.items()
        },
        "cards_legacy": {
            name: evaluate_cards(cards, train, args.test_season)
            for name, train in windows.items()
        },
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
