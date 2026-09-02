"""Fail-closed validation for a Cycle 41.1 service response or atomic run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.service.artifact_validation import (  # noqa: E402
    validate_service_response,
    validate_service_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.run_dir is not None:
        result = validate_service_run(args.run_dir)
    elif args.response is not None:
        result = validate_service_response(args.response, args.ledger)
    else:
        parser.error("provide --run-dir or --response")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
