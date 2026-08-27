"""Record one manually verified post-match result in the local shadow ledger."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.evaluation.manual_results import (
    ManualResultLedger,
    ManualResultRecord,
)

ROOT = Path(__file__).resolve().parents[2]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("timestamp must include explicit UTC, for example 2026-08-08T21:00:00Z")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction-id", required=True)
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--kickoff-utc", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--source-snapshot-id", required=True)
    parser.add_argument("--result-source", default="OpenLigaDB")
    parser.add_argument("--recorded-at-utc", default=None)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=ROOT / "data" / "shadow" / "manual_results.jsonl",
    )
    args = parser.parse_args()
    recorded_at = _utc(args.recorded_at_utc) if args.recorded_at_utc else datetime.now(UTC)
    record = ManualResultRecord(
        prediction_id=args.prediction_id,
        match_id=args.match_id,
        market=args.market,
        kickoff_utc=_utc(args.kickoff_utc),
        outcome_label=args.outcome,
        recorded_at_utc=recorded_at,
        result_source=args.result_source,
        source_snapshot_id=args.source_snapshot_id,
    )
    record_id = ManualResultLedger(args.ledger).append(record)
    print(json.dumps({"status": "recorded", "record_id": record_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
