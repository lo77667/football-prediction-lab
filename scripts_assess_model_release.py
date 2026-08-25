"""Assess whether walk-forward candidates pass the research release gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.learning.retraining import decide_walk_forward_retraining


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="reports/generated/walk_forward_ten_seasons.json")
    parser.add_argument("--output", default="reports/generated/model_release_assessment.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    report = json.loads((root / args.input).read_text(encoding="utf-8"))
    assessments = {
        "btts": _assess(report["btts"]["summary"], "legacy", "expanded"),
        "cards": _assess(
            report["cards"]["summary"], "legacy", "referee_enhanced"
        ),
    }
    result = {
        "policy": {
            "minimum_folds": 3,
            "minimum_rows": 500,
            "required_metrics": ["brier_score_mean", "log_loss_mean"],
            "accuracy_is_not_sufficient": True,
        },
        "assessments": assessments,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


def _assess(
    summaries: dict[str, dict[str, float | int]],
    baseline_name: str,
    candidate_name: str,
) -> dict[str, object]:
    decision = decide_walk_forward_retraining(
        summaries[baseline_name],
        summaries[candidate_name],
    )
    return {
        "baseline": baseline_name,
        "candidate": candidate_name,
        "accepted": decision.accepted,
        "reason": decision.reason,
        "baseline_summary": summaries[baseline_name],
        "candidate_summary": summaries[candidate_name],
    }


if __name__ == "__main__":
    raise SystemExit(main())
