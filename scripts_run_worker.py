"""Run the Cycle 44 local worker against deterministic local fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
)
from football_prediction_lab.worker import (
    FileLock,
    LocalWorker,
    StateStore,
    WorkerConfig,
    WorkerEvent,
    WorkerPrediction,
)

ROOT = Path(__file__).resolve().parent


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of-utc must be timezone-aware")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("dry-run", "shadow", "telegram-disabled"), default="dry-run"
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "reports" / "generated" / "cycle_44_worker_smoke"
    )
    parser.add_argument("--as-of-utc", default="2025-01-01T12:00:00Z")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    state_store = StateStore(output_root / "worker_state.json", output_root / "worker_events.jsonl")
    as_of = _parse_time(args.as_of_utc)
    kickoff = as_of + timedelta(days=1)

    def source(*, as_of_utc: datetime) -> list[WorkerEvent]:
        return [
            WorkerEvent(
                match_id="cycle44-fixture-001",
                market="btts",
                kickoff_utc=kickoff,
                observed_at_utc=as_of_utc,
                source_version="cycle44-local-fixture-v1",
            )
        ]

    def predictor(event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
        return WorkerPrediction(
            prediction_id=f"{event.match_id}:{event.market}",
            match_id=event.match_id,
            market=event.market,
            kickoff_utc=event.kickoff_utc,
            as_of_utc=as_of_utc,
            probability=0.62,
            model_version=MODEL_VERSION,
            policy_version=POLICY_VERSION,
            feature_version=FEATURE_VERSION,
        )

    notifications: list[str] = []

    def notifier(prediction: WorkerPrediction) -> str:
        notifications.append(prediction.prediction_id)
        return f"cycle44-fake-message-{len(notifications)}"

    config = WorkerConfig(
        mode=args.mode,
        polling_interval_seconds=args.interval_seconds,
        backoff_base_seconds=0.0,
    )
    worker = LocalWorker(
        state_store=state_store,
        lock=FileLock(output_root / "worker.lock"),
        config=config,
        source=source,
        predictor=predictor,
        notifier=notifier if args.mode == "shadow" else None,
        sleep_fn=lambda _: None,
        clock=lambda: as_of,
    )
    results = []
    for _ in range(args.iterations):
        results.append(worker.run_once(as_of_utc=as_of).__dict__)
    summary = {
        "mode": args.mode,
        "iterations": args.iterations,
        "results": results,
        "fake_notifications": len(notifications),
        "state_path": "worker_state.json",
        "events_path": "worker_events.jsonl",
        "network_scope": "none",
        "commercial_release": False,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
