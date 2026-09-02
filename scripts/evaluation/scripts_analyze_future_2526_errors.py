"""Analyze BTTS and cards errors on the frozen 2025/26 holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.features.cards import (
    LEGACY_CARD_FEATURE_COLUMNS,
    build_card_features,
)
from football_prediction_lab.learning.calibration import platt_calibrate
from football_prediction_lab.models.btts import LEGACY_FEATURE_COLUMNS, BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline

BANDS = [-0.001, 0.4, 0.6, 1.001]
BAND_LABELS = ["low", "medium", "high"]


def add_error_columns(
    frame: pd.DataFrame,
    *,
    target: str,
    probability_columns: list[str],
) -> pd.DataFrame:
    result = frame.copy()
    labels = result[target].astype(int)
    for column in probability_columns:
        probability = result[column].astype(float)
        decision = (probability >= 0.5).astype(int)
        result[f"{column}_decision"] = decision
        result[f"{column}_correct"] = (decision == labels).astype(int)
        result[f"{column}_absolute_error"] = (probability - labels).abs()
        result[f"{column}_brier_contribution"] = (probability - labels) ** 2
        result[f"{column}_log_loss_contribution"] = -(
            labels * np.log(np.clip(probability, 1e-15, 1 - 1e-15))
            + (1 - labels) * np.log(np.clip(1 - probability, 1e-15, 1 - 1e-15))
        )
        result[f"{column}_confidence"] = np.maximum(probability, 1 - probability)
    return result


def summarize(frame: pd.DataFrame, target: str, probability: str) -> dict[str, object]:
    labels = frame[target].astype(int)
    values = frame[probability].astype(float)
    decision = frame[f"{probability}_decision"]
    band = pd.cut(
        values,
        bins=BANDS,
        labels=BAND_LABELS,
        include_lowest=True,
    )
    grouped = (
        pd.DataFrame(
            {
                "band": band,
                "target": labels,
                "probability": values,
                "correct": (decision == labels).astype(int),
            }
        )
        .groupby("band", observed=False)
        .agg(
            rows=("target", "size"),
            actual_rate=("target", "mean"),
            mean_probability=("probability", "mean"),
            accuracy=("correct", "mean"),
        )
        .reset_index()
        .astype(object)
        .where(lambda value: pd.notna(value), None)
    )
    high_confidence = frame[frame[f"{probability}_confidence"] >= 0.7]
    return {
        "rows": len(frame),
        "actual_rate": float(labels.mean()),
        "accuracy": float((decision == labels).mean()),
        "brier_score": float(frame[f"{probability}_brier_contribution"].mean()),
        "log_loss": float(frame[f"{probability}_log_loss_contribution"].mean()),
        "mean_probability": float(values.mean()),
        "std_probability": float(values.std(ddof=0)),
        "min_probability": float(values.min()),
        "max_probability": float(values.max()),
        "near_half_fraction": float(values.between(0.45, 0.55).mean()),
        "high_confidence_rows": len(high_confidence),
        "high_confidence_accuracy": (
            float(high_confidence[f"{probability}_correct"].mean())
            if len(high_confidence)
            else None
        ),
        "false_positive": int(((decision == 1) & (labels == 0)).sum()),
        "false_negative": int(((decision == 0) & (labels == 1)).sum()),
        "by_probability_band": grouped.to_dict(orient="records"),
    }


def top_errors(frame: pd.DataFrame, probability: str, limit: int = 10) -> list[dict[str, object]]:
    columns = [
        "match_id",
        "kickoff_utc",
        "home_team",
        "away_team",
        "target",
        probability,
        f"{probability}_decision",
        f"{probability}_confidence",
        f"{probability}_brier_contribution",
    ]
    selected = frame.sort_values(f"{probability}_brier_contribution", ascending=False).head(limit)
    selected = selected[columns].assign(kickoff_utc=lambda value: value["kickoff_utc"].astype(str))
    return selected.to_dict(orient="records")


def fit_market(
    frame: pd.DataFrame,
    *,
    target: str,
    feature_columns: list[str],
    model_class: type,
    calibration_season: str,
    test_season: str,
) -> pd.DataFrame:
    seasons = sorted(frame["season"].astype(str).unique())
    calibration_index = seasons.index(calibration_season)
    train = frame[frame["season"].astype(str).isin(seasons[:calibration_index])]
    calibration = frame[frame["season"].astype(str) == calibration_season]
    test = frame[frame["season"].astype(str) == test_season].copy()
    model = model_class(feature_columns=feature_columns).fit(train)
    base_calibration = model.predict_probability(calibration)
    base_test = model.predict_probability(test)
    test["base_probability"] = base_test.to_numpy()
    test["platt_probability"] = platt_calibrate(
        base_calibration,
        calibration[target],
        base_test,
        c_value=1.0,
    ).to_numpy()
    constant_rate = float(pd.concat([train, calibration])[target].mean())
    test["constant_probability"] = constant_rate
    return test


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/epl_1516_2526.csv")
    parser.add_argument("--features", default="data/processed/epl_1516_2526_features.csv")
    parser.add_argument("--test-season", default="2526")
    parser.add_argument("--calibration-season", default="2425")
    parser.add_argument("--ledger-output", default="reports/generated/future_2526_error_ledger.csv")
    parser.add_argument(
        "--report-output", default="reports/generated/future_2526_error_analysis.json"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    normalized = pd.read_csv(root / args.input, parse_dates=["kickoff_utc"])
    btts_features = pd.read_csv(root / args.features, parse_dates=["kickoff_utc"])
    cards_features = build_card_features(normalized).merge(
        normalized[["match_id", "season"]],
        on="match_id",
        how="left",
        validate="one_to_one",
    )
    markets = {
        "btts": fit_market(
            btts_features,
            target="btts",
            feature_columns=LEGACY_FEATURE_COLUMNS,
            model_class=BttsLogisticBaseline,
            calibration_season=args.calibration_season,
            test_season=args.test_season,
        ),
        "cards": fit_market(
            cards_features,
            target="total_yellows_over_3_5",
            feature_columns=LEGACY_CARD_FEATURE_COLUMNS,
            model_class=TotalYellowCardsBaseline,
            calibration_season=args.calibration_season,
            test_season=args.test_season,
        ),
    }
    ledger_parts = []
    report_markets = {}
    for market, market_frame in markets.items():
        target = "btts" if market == "btts" else "total_yellows_over_3_5"
        market_frame = market_frame.rename(columns={target: "target"})
        market_frame["market"] = market
        market_frame = add_error_columns(
            market_frame,
            target="target",
            probability_columns=[
                "base_probability",
                "platt_probability",
                "constant_probability",
            ],
        )
        ledger_parts.append(market_frame)
        report_markets[market] = {
            probability: summarize(market_frame, "target", probability)
            for probability in (
                "base_probability",
                "platt_probability",
                "constant_probability",
            )
        }
        report_markets[market]["top_platt_errors"] = top_errors(market_frame, "platt_probability")
    ledger = pd.concat(ledger_parts, ignore_index=True)
    ledger_path = root / args.ledger_output
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(ledger_path, index=False)
    report = {
        "protocol": (
            "Frozen 2526 holdout; train before 2425, calibrate on 2425, "
            "inspect errors on 2526 only."
        ),
        "test_season": args.test_season,
        "calibration_season": args.calibration_season,
        "markets": report_markets,
        "ledger_path": args.ledger_output,
        "rows_in_ledger": len(ledger),
    }
    report_path = root / args.report_output
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"ledger_path={ledger_path}")
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
