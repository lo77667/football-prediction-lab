"""Paired bootstrap intervals for Platt versus constant cards probabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.features.cards import LEGACY_CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def _brier(probability: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((probability - target) ** 2))


def _log_loss(probability: np.ndarray, target: np.ndarray) -> float:
    clipped = np.clip(probability, 1e-15, 1.0 - 1e-15)
    return float(-np.mean(target * np.log(clipped) + (1.0 - target) * np.log(1.0 - clipped)))


def paired_bootstrap(
    folds: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    *,
    resamples: int,
    seed: int,
) -> dict[str, float | int]:
    rng = np.random.default_rng(seed)
    brier_deltas = np.empty(resamples)
    log_loss_deltas = np.empty(resamples)
    for iteration in range(resamples):
        brier_fold_deltas = []
        log_loss_fold_deltas = []
        for target, platt, constant in folds:
            indices = rng.integers(0, len(target), size=len(target))
            sampled_target = target[indices]
            brier_fold_deltas.append(
                _brier(platt[indices], sampled_target)
                - _brier(constant[indices], sampled_target)
            )
            log_loss_fold_deltas.append(
                _log_loss(platt[indices], sampled_target)
                - _log_loss(constant[indices], sampled_target)
            )
        brier_deltas[iteration] = np.mean(brier_fold_deltas)
        log_loss_deltas[iteration] = np.mean(log_loss_fold_deltas)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument(
        "--output", default="reports/generated/bootstrap_platt_cards_vs_constant.json"
    )
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.resamples < 1:
        parser.error("--resamples must be positive")

    root = Path(__file__).resolve().parents[2]
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    frame = build_card_features(matches).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    seasons = sorted(frame["season"].astype(str).unique())
    folds = []
    for index in range(2, len(seasons)):
        train = frame[frame["season"].astype(str).isin(seasons[: index - 1])]
        calibration = frame[frame["season"].astype(str) == seasons[index - 1]]
        test = frame[frame["season"].astype(str) == seasons[index]]
        model = TotalYellowCardsBaseline(feature_columns=LEGACY_CARD_FEATURE_COLUMNS).fit(train)
        calibrated = platt_calibrate(
            model.predict_probability(calibration),
            calibration["total_yellows_over_3_5"],
            model.predict_probability(test),
            c_value=1.0,
        )
        constant_rate = float(pd.concat([train, calibration])["total_yellows_over_3_5"].mean())
        folds.append(
            (
                test["total_yellows_over_3_5"].to_numpy(dtype=float),
                calibrated.to_numpy(dtype=float),
                np.full(len(test), constant_rate),
            )
        )

    result = {
        "protocol": (
            "Paired within-fold bootstrap; report macro-fold difference Platt minus "
            "constant for cards."
        ),
        "folds": len(folds),
        "rows": sum(len(target) for target, _, _ in folds),
        "candidate": "Platt sigmoid on LEGACY_CARD_FEATURE_COLUMNS, C=1.0",
        "baseline": "constant train-plus-calibration cards rate",
        "uncertainty": paired_bootstrap(folds, resamples=args.resamples, seed=args.seed),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
