"""Restore a local SQLite database only after integrity validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.storage import SQLiteStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    SQLiteStore.restore_from(args.backup.resolve(), args.database.resolve())
    result = SQLiteStore(args.database.resolve()).integrity_check()
    print(
        json.dumps(
            {"restore": "passed", "integrity": result, "commercial_release": False},
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
