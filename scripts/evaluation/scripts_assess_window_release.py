"""Assess nested window selection against a constant baseline on identical folds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scripts_walk_forward import evaluate_constant
from scripts_walk_forward_window_selected_btts import (
    CANDIDATE_WINDOWS,
    average_test_metrics,
    evaluate_model,
)

from football_prediction_lab.features.pre_match import (
    build_pre_match_features,
    feature_columns_for_window,
)
from football_prediction_lab.learning.retraining import decide_walk_forward_retraining


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument(
        "--selected-report",
        default="reports/generated/walk_forward_window_selected_btts_ten_seasons.json",
    )
    parser.add_argument(
        "--output",
        default="reports/generated/window_selected_release_decision.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    selected_report = json.loads((root / args.selected_report).read_text(encoding="utf-8"))
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    seasons = selected_report["seasons"]
    frames = {
        window: build_pre_match_features(matches, window=window).merge(
            matches[["match_id", "season"]],
            on="match_id",
            how="left",
            validate="one_to_one",
        )
        for window in CANDIDATE_WINDOWS
    }
    constant_folds = []
    fixed_folds: dict[str, list[dict[str, object]]] = {
        str(window): [] for window in CANDIDATE_WINDOWS
    }
    for index in range(2, len(seasons)):
        train_seasons = seasons[: index - 1]
        test_season = seasons[index]
        constant_folds.append(
            evaluate_constant(matches, "btts", train_seasons + [seasons[index - 1]], test_season)
        )
        for window, frame in frames.items():
            fixed_folds[str(window)].append(
                evaluate_model(
                    frame,
                    feature_columns_for_window(window),
                    train_seasons + [seasons[index - 1]],
                    test_season,
                )
            )

    baseline = average_test_metrics([{"test": fold} for fold in constant_folds])
    selected = selected_report["summary"]
    decision = decide_walk_forward_retraining(baseline, selected)
    result = {
        "protocol": (
            "Same 8 test seasons (1718 through 2425); selected-window fold outputs are "
            "compared with a constant baseline retrained through the same validation season."
        ),
        "baseline": baseline,
        "selected_nested_window": selected,
        "fixed_window_summaries": {
            window: average_test_metrics([{"test": fold} for fold in folds])
            for window, folds in fixed_folds.items()
        },
        "selected_window_counts": selected_report["selected_window_counts"],
        "accepted": decision.accepted,
        "reason": decision.reason,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
