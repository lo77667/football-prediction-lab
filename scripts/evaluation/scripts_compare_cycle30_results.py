"""Compare old published metrics with cycle-30 migration metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

METRICS = ("accuracy", "brier_score", "log_loss", "ece_10")


def _metric_block(report: dict, market: str, variant: str) -> dict[str, float | int]:
    block = report[market]["summary"].get(variant, {})
    return {
        metric: float(block[f"{metric}_mean"]) for metric in METRICS if f"{metric}_mean" in block
    }


def _future_block(report: dict, market: str, variant: str) -> dict[str, float | int]:
    block = report[market].get(variant, {})
    return {metric: float(block[metric]) for metric in METRICS if metric in block}


def _compare(old: dict[str, float | int], new: dict[str, float | int]) -> dict[str, object]:
    return {
        metric: {
            "old": old.get(metric),
            "new": new.get(metric),
            "delta_new_minus_old": (
                None
                if old.get(metric) is None or new.get(metric) is None
                else float(new[metric]) - float(old[metric])
            ),
        }
        for metric in METRICS
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-walk-forward", required=True)
    parser.add_argument("--new-walk-forward", required=True)
    parser.add_argument("--old-future", required=True)
    parser.add_argument("--new-future", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    old_wf = json.loads((root / args.old_walk_forward).read_text(encoding="utf-8"))
    new_wf = json.loads((root / args.new_walk_forward).read_text(encoding="utf-8"))
    old_future = json.loads((root / args.old_future).read_text(encoding="utf-8"))
    new_future = json.loads((root / args.new_future).read_text(encoding="utf-8"))
    variants = {
        "btts": ("constant_train_rate", "legacy", "expanded"),
        "cards": ("constant_train_rate", "legacy", "referee_enhanced"),
    }
    walk_forward = {
        market: {
            variant: _compare(
                _metric_block(old_wf, market, variant),
                _metric_block(new_wf, market, variant),
            )
            for variant in market_variants
        }
        for market, market_variants in variants.items()
    }
    future_variants = ("base", "platt", "constant_train_plus_calibration")
    future = {
        market: {
            variant: _compare(
                _future_block(old_future, market, variant),
                _future_block(new_future, market, variant),
            )
            for variant in future_variants
        }
        for market in ("btts", "cards")
    }
    result = {
        "purpose": "Migration audit only; no tuning, selection, or release decision.",
        "walk_forward_1516_2425": walk_forward,
        "future_2526": future,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
