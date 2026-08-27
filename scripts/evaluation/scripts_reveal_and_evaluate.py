"""Reveal outcomes after prediction and create evaluation reports."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from football_prediction_lab.contracts import OutcomeRecord
from football_prediction_lab.evaluation.metrics import evaluate_binary, reliability_table
from football_prediction_lab.ledger.append_only import PredictionLedger


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    data_path = root / "data" / "processed" / "2425_E0.csv"
    ledger_path = root / "reports" / "generated" / "predictions_only.jsonl"
    report_dir = root / "reports" / "generated"
    metrics_path = report_dir / "btts_metrics.json"
    reliability_path = report_dir / "btts_reliability.csv"
    errors_path = report_dir / "btts_errors.csv"

    matches = pd.read_csv(data_path, parse_dates=["kickoff_utc"]).set_index("match_id")
    ledger = PredictionLedger(ledger_path)
    for entry in ledger.records():
        if entry["record_type"] != "prediction":
            continue
        record = entry["record"]
        match = matches.loc[record["match_id"]]
        outcome = OutcomeRecord(
            prediction_id=record["prediction_id"],
            match_id=record["match_id"],
            market="btts",
            revealed_at_utc=match["kickoff_utc"].to_pydatetime() + timedelta(days=1),
            actual_yes=bool(match["btts"]),
            result_source=str(match["source"]),
        )
        if not any(
            item["record_type"] == "outcome" and item["record_id"] == outcome.prediction_id
            for item in ledger.records()
        ):
            ledger.append_outcome(outcome)

    ledger.verify()
    prediction_rows = {
        entry["record_id"]: entry["record"]
        for entry in ledger.records()
        if entry["record_type"] == "prediction"
    }
    outcome_rows = {
        entry["record_id"]: entry["record"]
        for entry in ledger.records()
        if entry["record_type"] == "outcome"
    }
    joined = []
    for prediction_id, prediction in prediction_rows.items():
        outcome = outcome_rows[prediction_id]
        probability = float(prediction["probability_yes"])
        actual = int(outcome["actual_yes"])
        decision = int(prediction["decision"] == "yes")
        joined.append(
            {
                "prediction_id": prediction_id,
                "match_id": prediction["match_id"],
                "probability_yes": probability,
                "actual_yes": actual,
                "decision": decision,
                "correct_decision": int(decision == actual),
                "absolute_error": abs(probability - actual),
            }
        )
    evaluation = pd.DataFrame(joined).sort_values("prediction_id").reset_index(drop=True)
    summary = evaluate_binary(evaluation["probability_yes"], evaluation["actual_yes"])
    reliability = reliability_table(evaluation["probability_yes"], evaluation["actual_yes"])
    metrics_path.write_text(json.dumps(summary.as_dict(), indent=2), encoding="utf-8")
    reliability.to_csv(reliability_path, index=False)
    evaluation.to_csv(errors_path, index=False)
    print(json.dumps(summary.as_dict(), sort_keys=True))
    print(f"outcome_records={len(outcome_rows)}")
    print(f"reliability_path={reliability_path}")
    print(f"errors_path={errors_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
