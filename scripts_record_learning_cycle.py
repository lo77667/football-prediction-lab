"""Classify real errors and record a conservative learning-cycle decision."""

from pathlib import Path

import pandas as pd

from football_prediction_lab.learning.error_log import classify_errors, write_learning_cycle


def main() -> int:
    root = Path(__file__).resolve().parent
    errors_path = root / "reports" / "generated" / "btts_errors.csv"
    classified_path = root / "reports" / "generated" / "btts_error_log.csv"
    learning_path = root / "reports" / "generated" / "learning_cycles.jsonl"
    errors = pd.read_csv(errors_path)
    classified = classify_errors(errors)
    classified.to_csv(classified_path, index=False)
    learning_path.unlink(missing_ok=True)
    write_learning_cycle(
        learning_path,
        source_evaluation="reports/generated/btts_metrics.json",
        parent_model_version="btts-logistic-v0.1",
        candidate_model_version="not-created",
        accepted=False,
        reason="no candidate was accepted: the untouched test window has only 57 rows",
    )
    print(f"classified_errors={len(classified)}")
    print(f"false_positive={int((classified['error_type'] == 'false_positive').sum())}")
    print(f"false_negative={int((classified['error_type'] == 'false_negative').sum())}")
    print(f"learning_cycle={learning_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
