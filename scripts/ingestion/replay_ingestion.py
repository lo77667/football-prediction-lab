"""Replay validation for an existing deterministic Cycle 38 ingestion manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.ingestion.local_csv import replay_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    result = replay_manifest(Path(args.manifest))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
