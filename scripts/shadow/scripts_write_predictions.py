"""Write point-in-time predictions without writing outcomes."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from football_prediction_lab.contracts import PredictionRecord
from football_prediction_lab.ledger.append_only import PredictionLedger
from football_prediction_lab.models.btts import BttsLogisticBaseline, temporal_split


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    input_path = root / "data" / "processed" / "2425_E0_features.csv"
    ledger_path = root / "reports" / "generated" / "predictions_only.jsonl"
    ledger_path.unlink(missing_ok=True)

    frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
    split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
    model = BttsLogisticBaseline().fit(split.train)
    probabilities = model.predict_probability(split.test)
    ledger = PredictionLedger(ledger_path)

    for row, probability in zip(split.test.itertuples(index=False), probabilities, strict=True):
        kickoff = pd.Timestamp(row.kickoff_utc).to_pydatetime()
        feature_values = {column: getattr(row, column) for column in model_feature_columns()}
        fingerprint = hashlib.sha256(
            json.dumps(feature_values, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        record = PredictionRecord(
            prediction_id=f"btts-{row.match_id}",
            match_id=row.match_id,
            market="btts",
            predicted_at_utc=kickoff - timedelta(minutes=1),
            model_version=model.model_version,
            feature_version=model.feature_version,
            probability_yes=float(probability),
            decision="yes" if probability >= 0.5 else "no",
            data_cutoff_utc=kickoff,
            input_fingerprint=fingerprint,
        )
        ledger.append_prediction(record)

    ledger.verify()
    print(f"prediction_records={len(ledger.records())}")
    print(f"outcome_records={sum(entry['record_type'] == 'outcome' for entry in ledger.records())}")
    print(f"ledger_path={ledger_path}")
    return 0


def model_feature_columns() -> list[str]:
    return [
        "home_avg_scored",
        "home_avg_conceded",
        "home_btts_rate",
        "away_avg_scored",
        "away_avg_conceded",
        "away_btts_rate",
        "home_matches_before",
        "away_matches_before",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
