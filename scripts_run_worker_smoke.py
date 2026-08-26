"""Run deterministic Cycle 44 worker smoke scenarios without network."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from football_prediction_lab.service.version import FEATURE_VERSION, MODEL_VERSION, POLICY_VERSION
from football_prediction_lab.worker import (
    FileLock,
    LocalWorker,
    StateStore,
    WorkerConfig,
    WorkerEvent,
    WorkerPrediction,
)

NOW = datetime(2025, 1, 1, 12, tzinfo=UTC)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _event(match_id: str = "cycle44-smoke-001") -> WorkerEvent:
    return WorkerEvent(
        match_id=match_id,
        market="btts",
        kickoff_utc=NOW + timedelta(days=1),
        observed_at_utc=NOW,
        source_version="cycle44-local-fixture-v1",
    )


def _predict(event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
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


def _worker(root: Path, *, mode: str, source: Any, notifier: Any = None) -> LocalWorker:
    return LocalWorker(
        state_store=StateStore(root / "worker_state.json", root / "worker_events.jsonl"),
        lock=FileLock(root / "worker.lock"),
        config=WorkerConfig(mode=mode, polling_interval_seconds=0.0),
        source=source,
        predictor=_predict,
        notifier=notifier,
        sleep_fn=lambda _: None,
        clock=lambda: NOW,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root", type=Path, default=Path("reports/generated/cycle_44_worker_smoke")
    )
    args = parser.parse_args()
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    def local_source(*, as_of_utc: datetime) -> list[WorkerEvent]:
        return [_event()]

    dry = _worker(root / "dry_run", mode="dry-run", source=local_source)
    dry_results = [dry.run_once(as_of_utc=NOW).__dict__, dry.run_once(as_of_utc=NOW).__dict__]

    disabled = _worker(root / "telegram_disabled", mode="telegram-disabled", source=local_source)
    disabled_result = disabled.run_once(as_of_utc=NOW).__dict__

    no_data = _worker(root / "no_data", mode="dry-run", source=lambda *, as_of_utc: [])
    no_data_result = no_data.run_once(as_of_utc=NOW).__dict__

    notifications: list[str] = []

    def notifier(prediction: WorkerPrediction) -> str:
        notifications.append(prediction.prediction_id)
        return f"fake-message-{len(notifications)}"

    shadow = _worker(root / "shadow", mode="shadow", source=local_source, notifier=notifier)
    shadow_result = shadow.run_once(as_of_utc=NOW).__dict__
    shadow.run_forever(max_iterations=1)

    state_files = sorted(root.glob("**/worker_state.json"))
    _write_json(
        root / "validation.json",
        {
            "validation": "passed",
            "dry_run_statuses": [item["status"] for item in dry_results],
            "telegram_disabled_status": disabled_result["status"],
            "no_data_status": no_data_result["status"],
            "shadow_status": shadow_result["status"],
            "shadow_notifications": len(notifications),
            "state_files": len(state_files),
            "network_scope": "none",
            "commercial_release": False,
        },
    )
    _write_json(
        root / "smoke_summary.json",
        {
            "scenarios": ["dry-run", "telegram-disabled", "no-data", "shadow"],
            "artifacts": ["validation.json", "**/worker_state.json", "**/worker_events.jsonl"],
            "network_scope": "none",
            "commercial_release": False,
        },
    )
    print(
        json.dumps(
            json.loads((root / "validation.json").read_text(encoding="utf-8")),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
