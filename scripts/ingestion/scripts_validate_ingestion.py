"""Validate one Cycle 38 ingestion manifest and referenced files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.ingestion.local_csv import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    manifest = validate_manifest(Path(args.manifest))
    result = {
        "validation": "passed",
        "manifest_path": str(Path(args.manifest).resolve()),
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "input_sha256": manifest["input_sha256"],
        "output_sha256": manifest["run"]["output_hash"],
        "rows_read": manifest["run"]["rows_read"],
        "rows_accepted": manifest["run"]["rows_accepted"],
        "rows_quarantined": manifest["run"]["rows_quarantined"],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
