"""Produce a deterministic Cycle 46 source-readiness report without network."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from football_prediction_lab.source import LocalJsonlSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--source-version", default="fixture-v1")
    parser.add_argument("--as-of-utc", default="2025-01-01T12:00:00+00:00")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/generated/cycle_46_source_readiness.json")
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "cycle": "46",
        "external_source_status": "deferred_missing_authorized_source",
        "provider": None,
        "dataset_or_endpoint": None,
        "license": None,
        "allowed_reuse": False,
        "verified_snapshots": 0,
        "shadow_status": "deferred",
        "source_version": None,
        "input_sha256": None,
        "accepted_rows": 0,
        "quarantined_rows": 0,
        "quarantine_reasons": {},
        "network_calls": 0,
        "commercial_release": False,
    }
    if args.input is not None:
        as_of = datetime.fromisoformat(args.as_of_utc)
        source = LocalJsonlSource(args.input.resolve(), source_version=args.source_version)
        batch = source.read(as_of_utc=as_of)
        reasons: dict[str, int] = {}
        for row in batch.quarantined:
            reasons[row.reason] = reasons.get(row.reason, 0) + 1
        report.update(
            {
                "external_source_status": "local_fixture_only",
                "source_version": batch.source_version,
                "input_sha256": batch.input_sha256,
                "accepted_rows": len(batch.rows),
                "quarantined_rows": len(batch.quarantined),
                "quarantine_reasons": dict(sorted(reasons.items())),
                "shadow_status": "shadow_fixture_only" if batch.rows else "deferred",
            }
        )
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
