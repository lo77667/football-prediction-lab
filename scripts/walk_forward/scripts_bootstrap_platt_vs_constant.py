"""Paired bootstrap intervals for Platt versus constant BTTS probabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.features.pre_match import build_pre_match_features
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline


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
) -> dict[str, float | int | list[float]]:
    rng = np.random.default_rng(seed)
    deltas_brier = np.empty(resamples)
    deltas_log_loss = np.empty(resamples)
    for iteration in range(resamples):
        brier_deltas = []
        log_loss_deltas = []
        for target, platt, constant in folds:
            indices = rng.integers(0, len(target), size=len(target))
            sampled_target = target[indices]
            brier_deltas.append(
                _brier(platt[indices], sampled_target)
                - _brier(constant[indices], sampled_target)
            )
            log_loss_deltas.append(
                _log_loss(platt[indices], sampled_target)
                - _log_loss(constant[indices], sampled_target)
            )
        deltas_brier[iteration] = np.mean(brier_deltas)
        deltas_log_loss[iteration] = np.mean(log_loss_deltas)

    return {
        "resamples": resamples,
        "seed": seed,
        "brier_delta_mean": float(np.mean(deltas_brier)),
        "brier_delta_percentile_2_5": float(np.percentile(deltas_brier, 2.5)),
        "brier_delta_percentile_97_5": float(np.percentile(deltas_brier, 97.5)),
        "log_loss_delta_mean": float(np.mean(deltas_log_loss)),
        "log_loss_delta_percentile_2_5": float(np.percentile(deltas_log_loss, 2.5)),
        "log_loss_delta_percentile_97_5": float(np.percentile(deltas_log_loss, 97.5)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2425.csv")
    parser.add_argument("--output", default="reports/generated/bootstrap_platt_vs_constant.json")
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.resamples < 1:
        parser.error("--resamples must be positive")

    root = Path(__file__).resolve().parents[2]
    matches = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    features = build_pre_match_features(matches, window=(5, 10)).merge(
        matches[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    seasons = sorted(matches["season"].astype(str).unique())
    folds: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for index in range(2, len(seasons)):
        train_seasons = seasons[: index - 1]
        calibration_season = seasons[index - 1]
        test_season = seasons[index]
        train = features[features["season"].astype(str).isin(train_seasons)]
        calibration = features[features["season"].astype(str) == calibration_season]
        test = features[features["season"].astype(str) == test_season]
        model = BttsLogisticBaseline(feature_columns=LEGACY_FEATURE_COLUMNS).fit(train)
        calibration_probability = model.predict_probability(calibration)
        platt_probability = platt_calibrate(
            calibration_probability,
            calibration["btts"],
            model.predict_probability(test),
            c_value=1.0,
        )
        constant_rate = float(pd.concat([train, calibration])["btts"].mean())
        constant_probability = np.full(len(test), constant_rate)
        folds.append(
            (
                test["btts"].to_numpy(dtype=float),
                platt_probability.to_numpy(dtype=float),
                constant_probability,
            )
        )

    result = {
        "protocol": (
            "Within each of 8 temporal test folds, resample held-out rows in paired "
            "fashion; report the macro-fold difference Platt minus constant."
        ),
        "folds": len(folds),
        "rows": sum(len(target) for target, _, _ in folds),
        "candidate": "Platt sigmoid on LEGACY_FEATURE_COLUMNS, C=1.0",
        "baseline": "constant train-plus-calibration BTTS rate",
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
