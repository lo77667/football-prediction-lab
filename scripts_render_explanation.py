"""Render a grounded explanation from the verified metrics JSON."""

import json
from pathlib import Path

from football_prediction_lab.agent.explanation import VerifiedEvaluation, render_verified_summary


def main() -> int:
    root = Path(__file__).resolve().parent
    metrics_path = root / "reports" / "generated" / "btts_metrics.json"
    output_path = root / "reports" / "generated" / "btts_explanation.txt"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    allowed = {
        "rows",
        "accuracy",
        "brier_score",
        "log_loss",
        "actual_rate",
        "mean_probability",
    }
    evaluation = VerifiedEvaluation(
        market="btts",
        model_version="btts-logistic-v0.1",
        **{key: metrics[key] for key in allowed},
    )
    summary = render_verified_summary(evaluation)
    output_path.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"output_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
