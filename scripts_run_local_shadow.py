"""Run bounded local OpenLigaDB shadow ingestion with a file-based kill switch."""

from __future__ import annotations

import argparse
import json
import signal
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from football_prediction_lab.source import OpenLigaDBClient, OpenLigaDBShadowIngestor
from football_prediction_lab.storage import SQLiteStore

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "reports" / "local_shadow")
    parser.add_argument("--interval-seconds", type=float, default=3600.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if args.interval_seconds < 0 or args.iterations < 1:
        parser.error("--interval-seconds must be non-negative and --iterations must be positive")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stop_file = (args.stop_file or output_root / "STOP").resolve()
    stopped = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signum, _frame: stopped.set())

    if not args.allow_network:
        print(
            json.dumps(
                {
                    "status": "deferred_network_disabled",
                    "stop_file": str(stop_file),
                    "commercial_release": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0

    database = output_root / "shadow.sqlite3"
    ingestor = OpenLigaDBShadowIngestor(
        client=OpenLigaDBClient(
            allow_network=True,
            timeout_seconds=10.0,
            min_interval_seconds=1.0,
        ),
        store=SQLiteStore(database),
    )
    runs: list[dict[str, object]] = []
    for iteration in range(1, args.iterations + 1):
        if stopped.is_set() or stop_file.exists():
            break
        result = ingestor.run_once(as_of_utc=datetime.now(UTC))
        runs.append({"iteration": iteration, **result.__dict__})
        if iteration < args.iterations and not stopped.wait(args.interval_seconds):
            continue
        break
    status = "stopped" if stopped.is_set() or stop_file.exists() else "completed"
    summary = {
        "status": status,
        "iterations_requested": args.iterations,
        "iterations_completed": len(runs),
        "runs": runs,
        "stop_file": str(stop_file),
        "database_path": str(database),
        "network_opt_in": True,
        "telegram_enabled": False,
        "commercial_release": False,
    }
    summary_path = output_root / "latest_run.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {**summary, "summary_path": str(summary_path)},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
