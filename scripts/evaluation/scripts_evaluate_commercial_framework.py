"""Build a leakage-safe commercial evaluation report; no execution or staking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from football_prediction_lab.data.provenance import build_manifest, sha256_file, write_manifest
from football_prediction_lab.evaluation.metrics import evaluate_binary_extended

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "generated"
MARKETS = {
    "btts": {
        "path": REPORTS / "btts_ten_seasons_holdout.csv",
        "target": "btts",
    },
    "cards": {
        "path": REPORTS / "cards_ten_seasons_holdout.csv",
        "target": "total_yellows_over_3_5",
    },
}


def point_in_time_rate(target: pd.Series) -> pd.Series:
    """Rate from strictly earlier rows; first row has no benchmark."""

    values = target.astype(float).to_numpy()
    cumulative = np.cumsum(values)
    counts = np.arange(len(values), dtype=float)
    result = np.full(len(values), np.nan)
    valid = counts > 0
    result[valid] = cumulative[:-1][valid[1:]] / counts[valid]
    return pd.Series(result, index=target.index, dtype=float)


def evaluate_market(
    market: str, config: dict[str, object]
) -> tuple[dict[str, object], pd.DataFrame]:
    frame = pd.read_csv(config["path"], parse_dates=["kickoff_utc"])
    frame = frame.sort_values(["kickoff_utc", "match_id"], kind="mergesort").reset_index(drop=True)
    if "season" not in frame:
        season_map = pd.read_csv(
            MARKETS["btts"]["path"], usecols=["match_id", "season"]
        ).drop_duplicates("match_id")
        frame = frame.merge(season_map, on="match_id", how="left")
    if (frame["season"].astype(str) == "2526").any():
        raise ValueError("2526 is a final holdout and must not enter this report")
    target = frame[config["target"]].astype(int)
    probability = frame["probability_yes"].astype(float)
    baseline = point_in_time_rate(target)
    valid = baseline.notna() & probability.notna()
    evaluated = frame.loc[valid, ["match_id", "kickoff_utc", "season"]].copy()
    evaluated["actual"] = target.loc[valid].to_numpy()
    evaluated["model_probability"] = probability.loc[valid].to_numpy()
    evaluated["baseline_probability"] = baseline.loc[valid].to_numpy()
    evaluated["model_brier"] = (evaluated["model_probability"] - evaluated["actual"]) ** 2
    evaluated["baseline_brier"] = (evaluated["baseline_probability"] - evaluated["actual"]) ** 2
    evaluated["model_log_loss"] = -(
        evaluated["actual"] * np.log(np.clip(evaluated["model_probability"], 1e-15, 1 - 1e-15))
        + (1 - evaluated["actual"])
        * np.log(np.clip(1 - evaluated["model_probability"], 1e-15, 1 - 1e-15))
    )
    evaluated["baseline_log_loss"] = -(
        evaluated["actual"] * np.log(np.clip(evaluated["baseline_probability"], 1e-15, 1 - 1e-15))
        + (1 - evaluated["actual"])
        * np.log(np.clip(1 - evaluated["baseline_probability"], 1e-15, 1 - 1e-15))
    )
    overall = evaluate_binary_extended(
        evaluated["model_probability"],
        evaluated["actual"],
        baseline_probability=evaluated["baseline_probability"],
        expected_rows=len(frame),
    )
    overall["baseline_rows"] = int(len(evaluated))
    overall["excluded_first_row_without_history"] = int(len(frame) - len(evaluated))
    by_season: dict[str, object] = {}
    for season, group in evaluated.groupby("season", sort=True):
        metrics = evaluate_binary_extended(
            group["model_probability"],
            group["actual"],
            baseline_probability=group["baseline_probability"],
        )
        by_season[str(season)] = metrics
    evaluated.insert(0, "market", market)
    return (
        {"market": market, "rows": int(len(frame)), "overall": overall, "by_season": by_season},
        evaluated,
    )


def main() -> None:
    results: list[dict[str, object]] = []
    ledgers: list[pd.DataFrame] = []
    for market, config in MARKETS.items():
        result, ledger = evaluate_market(market, config)
        results.append(result)
        ledgers.append(ledger)
    REPORTS.mkdir(parents=True, exist_ok=True)
    ledger = pd.concat(ledgers, ignore_index=True)
    ledger.to_csv(REPORTS / "cycle_31_commercial_ledger.csv", index=False)
    report = {
        "cycle": 31,
        "scope": "available historical holdout rows, excluding protected 2526",
        "financial_execution": False,
        "live_odds_used": False,
        "holdout_2526_policy": "excluded and protected",
        "benchmark_definition": (
            "strictly prior observed outcomes in deterministic kickoff_utc, match_id order"
        ),
        "markets": results,
    }
    report_path = REPORTS / "cycle_31_commercial_evaluation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    input_digests = "".join(
        f"{market}:{sha256_file(config['path'])};" for market, config in MARKETS.items()
    )
    input_sha256 = hashlib.sha256(input_digests.encode("utf-8")).hexdigest()
    manifest_dir = REPORTS / "manifests"
    for output_path in (report_path, REPORTS / "cycle_31_commercial_ledger.csv"):
        manifest = build_manifest(
            input_path=";".join(str(config["path"]) for config in MARKETS.values()),
            input_sha256=input_sha256,
            output_path=str(output_path),
            rows_before=sum(result["rows"] for result in results),
            rows_after=len(ledger),
            frame=ledger,
            feature_version="commercial-evaluation-v1",
        )
        write_manifest(manifest, manifest_dir / f"{output_path.stem}.manifest.json")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
