from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.shadow.runner import run_shadow  # noqa: E402


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
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
        type=Path,
        default=ROOT / "configs" / "cycle36_future_holdout_policy.json",
    )
    parser.add_argument("--training-cutoff", type=_parse_datetime)
    args = parser.parse_args()
    result = run_shadow(
        manifest_path=args.manifest,
        as_of_utc=args.as_of,
        run_id=args.run_id,
        output_root=args.output_root,
        policy_path=args.policy,
        training_cutoff=args.training_cutoff,
    )
    run = result["run"]
    print(f"predictions_path={result['predictions_path']}")
    print(f"run_path={result['run_path']}")
    print(f"ledger_path={result['ledger_path']}")
    print(f"rows_seen={run['rows_seen']}")
    print(f"predictions_issued={run['predictions_issued']}")
    print(f"rows_skipped={run['rows_skipped']}")
    print(f"output_sha256={run['output_sha256']}")
    print(f"ledger_sha256={run['ledger_sha256']}")
    print(f"status={run['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
