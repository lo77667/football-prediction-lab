"""Generate a validation report from walk-forward JSON results.

Reads reports/generated/walk_forward_results.json and produces reports/generated/validation_report.md
with aggregated Brier Score and Log Loss comparisons between the logistic baseline (expanded), XGBoost,
and LightGBM.

Exit code: 0 always (we want the workflow to continue). The workflow will commit the generated report
and upload it as an artifact.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = ROOT / "reports" / "generated" / "walk_forward_results.json"
REPORT_PATH = ROOT / "reports" / "generated" / "validation_report.md"


def mean_safe(values: List[float]) -> float:
    return float(statistics.mean(values)) if values else float("nan")


def extract_metrics(results: Dict) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    btts = results.get("btts", {}).get("variants", {})
    for variant, records in btts.items():
        brier_vals = []
        logloss_vals = []
        for rec in records:
            try:
                brier_vals.append(float(rec.get("brier_score")))
            except Exception:
                pass
            try:
                logloss_vals.append(float(rec.get("log_loss")))
            except Exception:
                pass
        out[variant] = {
            "brier_mean": mean_safe(brier_vals),
            "logloss_mean": mean_safe(logloss_vals),
            "folds": len(records),
        }
    return out


def verdict(model_metrics: Dict[str, float], baseline_metrics: Dict[str, float]) -> str:
    # lower is better for both metrics
    brier_ok = model_metrics["brier_mean"] <= baseline_metrics["brier_mean"]
    logloss_ok = model_metrics["logloss_mean"] <= baseline_metrics["logloss_mean"]
    if brier_ok and logloss_ok:
        return "PASS"
    reasons = []
    if not brier_ok:
        reasons.append("higher Brier score")
    if not logloss_ok:
        reasons.append("higher Log Loss")
    return "FAIL (" + ", ".join(reasons) + ")"


def make_report(results: Dict) -> str:
    metrics = extract_metrics(results)
    baseline = metrics.get("expanded") or metrics.get("legacy") or {}
    lines = ["# Walk-forward Validation Report", "", "## Summary metrics (lower is better)", ""]
    lines.append("| Variant | Brier Score (mean) | Log Loss (mean) | Folds |")
    lines.append("|---|---:|---:|---:|")
    for variant in sorted(metrics.keys()):
        m = metrics[variant]
        lines.append(f"| {variant} | {m['brier_mean']:.6f} | {m['logloss_mean']:.6f} | {m['folds']} |")
    lines.append("")
    lines.append("## Verdict vs logistic baseline (expanded)")
    lines.append("")
    if not baseline:
        lines.append("Baseline (expanded) metrics not found in results. Cannot compute verdict.")
        return "\n".join(lines)
    for variant in ("xgboost", "lightgbm"):
        if variant in metrics:
            v = metrics[variant]
            v_str = verdict(v, baseline)
            lines.append(f"- **{variant}**: {v_str} — Brier {v['brier_mean']:.6f} vs baseline {baseline['brier_mean']:.6f}; "
                         f"LogLoss {v['logloss_mean']:.6f} vs baseline {baseline['logloss_mean']:.6f}.")
        else:
            lines.append(f"- **{variant}**: not present in results")
    lines.append("")
    # Recommendation
    pass_count = sum(1 for variant in ("xgboost", "lightgbm") if variant in metrics and verdict(metrics[variant], baseline).startswith("PASS"))
    lines.append("## Recommendation")
    if pass_count == 2:
        lines.append("Both XGBoost and LightGBM meet or improve on the logistic baseline calibration. Proceed to Phase 2 (bot + scheduler) under shadow mode.")
    elif pass_count == 1:
        lines.append("One model passes against the logistic baseline. Recommend: proceed with the passing model for Phase 2, and further tune the other model (reduce n_estimators or increase regularization).")
    else:
        lines.append("Neither model improves over the logistic baseline. Do NOT proceed to automation. Tune hyperparameters (reduce n_estimators, increase reg_alpha/reg_lambda) and re-run evaluation.")
    return "\n".join(lines)


def main() -> int:
    if not RESULTS_PATH.exists():
        print(f"Results not found at {RESULTS_PATH}")
        return 1
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    report = make_report(data)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
