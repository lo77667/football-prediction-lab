"""Paired bootstrap uncertainty for the 2025/26 future holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.features.cards import LEGACY_CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def _brier(probability: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((probability - target) ** 2))


def _log_loss(probability: np.ndarray, target: np.ndarray) -> float:
    clipped = np.clip(probability, 1e-15, 1.0 - 1e-15)
    return float(-np.mean(target * np.log(clipped) + (1.0 - target) * np.log(1.0 - clipped)))


def bootstrap_difference(
    target: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    resamples: int,
    seed: int,
) -> dict[str, float | int]:
    rng = np.random.default_rng(seed)
    brier_deltas = np.empty(resamples)
    log_loss_deltas = np.empty(resamples)
    for iteration in range(resamples):
        indices = rng.integers(0, len(target), size=len(target))
        sampled_target = target[indices]
        brier_deltas[iteration] = _brier(candidate[indices], sampled_target) - _brier(
            baseline[indices], sampled_target
        )
        log_loss_deltas[iteration] = _log_loss(candidate[indices], sampled_target) - _log_loss(
            baseline[indices], sampled_target
        )
    return {
        "resamples": resamples,
        "seed": seed,
        "brier_delta_mean": float(np.mean(brier_deltas)),
        "brier_delta_percentile_2_5": float(np.percentile(brier_deltas, 2.5)),
        "brier_delta_percentile_97_5": float(np.percentile(brier_deltas, 97.5)),
        "log_loss_delta_mean": float(np.mean(log_loss_deltas)),
        "log_loss_delta_percentile_2_5": float(np.percentile(log_loss_deltas, 2.5)),
        "log_loss_delta_percentile_97_5": float(np.percentile(log_loss_deltas, 97.5)),
    }


def probabilities(
    frame: pd.DataFrame,
    target: str,
    feature_columns: list[str],
    model_class: type,
    calibration_season: str,
    test_season: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    seasons = sorted(frame["season"].astype(str).unique())
    calibration_index = seasons.index(calibration_season)
    train = frame[frame["season"].astype(str).isin(seasons[:calibration_index])]
    calibration = frame[frame["season"].astype(str) == calibration_season]
    test = frame[frame["season"].astype(str) == test_season]
    model = model_class(feature_columns=feature_columns).fit(train)
    calibrated = platt_calibrate(
        model.predict_probability(calibration),
        calibration[target],
        model.predict_probability(test),
        c_value=1.0,
    )
    constant_rate = float(pd.concat([train, calibration])[target].mean())
    return (
        test[target].to_numpy(dtype=float),
        calibrated.to_numpy(dtype=float),
        np.full(len(test), constant_rate),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2526.csv")
    parser.add_argument("--features", default="data/processed/epl_1516_2526_features.csv")
    parser.add_argument("--calibration-season", default="2425")
    parser.add_argument("--test-season", default="2526")
    parser.add_argument("--output", default="reports/generated/bootstrap_future_2526.json")
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.resamples < 1:
        parser.error("--resamples must be positive")

    root = Path(__file__).resolve().parents[2]
    normalized = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    btts_frame = pd.read_csv(root / args.features, parse_dates=["kickoff_utc"])
    cards_frame = build_card_features(normalized).merge(
        normalized[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    results = {}
    for market, frame, target, columns, model in (
        ("btts", btts_frame, "btts", LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline),
        (
            "cards",
            cards_frame,
            "total_yellows_over_3_5",
            LEGACY_CARD_FEATURE_COLUMNS,
            TotalYellowCardsBaseline,
        ),
    ):
        target_values, candidate, baseline = probabilities(
            frame,
            target,
            columns,
            model,
            args.calibration_season,
            args.test_season,
        )
        results[market] = {
            "target": target,
            "rows": len(target_values),
            "candidate": "Platt sigmoid, C=1.0",
            "baseline": "constant train-plus-calibration rate",
            "uncertainty": bootstrap_difference(
                target_values,
                candidate,
                baseline,
                resamples=args.resamples,
                seed=args.seed,
            ),
        }
    report = {
        "protocol": (
            "Paired bootstrap within unseen 2526 test rows; candidate and constant "
            "see identical resampled rows."
        ),
        "calibration_season": args.calibration_season,
        "test_season": args.test_season,
        "results": results,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
