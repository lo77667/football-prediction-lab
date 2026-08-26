"""Replay one Cycle 39 shadow run locally with explicit as-of and training cutoff."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.shadow.runner import run_shadow  # noqa: E402


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--as-of", required=True, type=_parse_datetime)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--policy",
        required=False,
        type=Path,
        default=ROOT / "configs" / "cycle36_future_holdout_policy.json",
    )
    parser.add_argument("--training-cutoff", required=True, type=_parse_datetime)
    args = parser.parse_args()
    result = run_shadow(
        manifest_path=args.manifest,
        as_of_utc=args.as_of,
        run_id=args.run_id,
        output_root=args.output_root,
        policy_path=args.policy,
        training_cutoff=args.training_cutoff,
    )
    print(
        json.dumps(
            {
                "replay": "passed",
                "predictions_path": result["predictions_path"],
                "run_path": result["run_path"],
                "ledger_path": result["ledger_path"],
                "output_sha256": result["run"]["output_sha256"],
                "ledger_sha256": result["run"]["ledger_sha256"],
                "predictions_issued": result["run"]["predictions_issued"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
