"""Create an integrity-checked local SQLite backup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.storage import SQLiteStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    store = SQLiteStore(args.database.resolve())
    before = store.integrity_check()
    if not before["passed"]:
        raise SystemExit("source database failed integrity check")
    store.backup_to(args.backup.resolve())
    after = SQLiteStore(args.backup.resolve()).integrity_check()
    print(
        json.dumps(
            {"backup": str(args.backup.name), "integrity": after, "commercial_release": False},
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
