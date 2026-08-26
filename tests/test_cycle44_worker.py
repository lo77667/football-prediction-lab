from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from football_prediction_lab.worker import (
    FileLock,
    LocalWorker,
    StateStore,
    WorkerAlreadyRunning,
    WorkerConfig,
    WorkerError,
    WorkerEvent,
    WorkerPrediction,
)

NOW = datetime(2025, 1, 1, 12, tzinfo=UTC)


def _event(*, match_id: str = "match-001", kickoff: datetime | None = None) -> WorkerEvent:
    return WorkerEvent(
        match_id=match_id,
        market="btts",
        kickoff_utc=kickoff or NOW + timedelta(hours=3),
        observed_at_utc=NOW,
        source_version="fixture-v1",
    )


def _predictor(event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
    return WorkerPrediction(
        prediction_id=f"{event.match_id}:{event.market}",
        match_id=event.match_id,
        market=event.market,
        kickoff_utc=event.kickoff_utc,
        as_of_utc=as_of_utc,
        probability=0.62,
        model_version="model-v1",
        policy_version="policy-v1",
        feature_version="feature-v1",
    )


def _worker(
    tmp_path: Path,
    *,
    source: Any = None,
    predictor: Any = _predictor,
    notifier: Any = None,
    mode: str = "dry-run",
    config_overrides: dict[str, Any] | None = None,
    sleep_fn: Any = lambda _: None,
) -> LocalWorker:
    root = tmp_path / "worker"
    config = WorkerConfig(mode=mode, **(config_overrides or {}))
    return LocalWorker(
        state_store=StateStore(root / "state.json", root / "events.jsonl"),
        lock=FileLock(root / "worker.lock"),
        config=config,
        source=source or (lambda *, as_of_utc: [_event()]),
        predictor=predictor,
        notifier=notifier,
        sleep_fn=sleep_fn,
        clock=lambda: NOW,
    )


def test_dry_run_issues_once_then_deduplicates(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    first = worker.run_once(as_of_utc=NOW)
    second = worker.run_once(as_of_utc=NOW)
    assert first.status == "completed"
    assert first.predictions_issued == 1
    assert second.skipped_events == 1
    assert second.predictions_issued == 0
    state = worker.state_store.load()
    assert state.processed_event_keys == ["match-001:btts"]
    assert state.prediction_keys == ["match-001:btts"]
    assert state.last_heartbeat_utc == NOW.isoformat()


def test_telegram_disabled_skips_notification_without_client(tmp_path: Path) -> None:
    worker = _worker(tmp_path, mode="telegram-disabled")
    result = worker.run_once(as_of_utc=NOW)
    assert result.status == "completed"
    assert result.notifications_sent == 1
    events = worker.state_store.events()
    assert any(event.get("reason") == "telegram_disabled" for event in events)


def test_shadow_requires_injected_notifier(tmp_path: Path) -> None:
    with pytest.raises(WorkerError, match="notifier"):
        _worker(tmp_path, mode="shadow")


def test_shadow_notifier_failure_retries_and_dead_letters(tmp_path: Path) -> None:
    calls = 0

    def notifier(_: WorkerPrediction) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("remote failure")

    worker = _worker(
        tmp_path,
        mode="shadow",
        notifier=notifier,
        config_overrides={"max_attempts": 2, "circuit_failure_threshold": 5},
    )
    result = worker.run_once(as_of_utc=NOW)
    assert result.status == "partial_data"
    assert result.failures == 1
    assert calls == 2
    state = worker.state_store.load()
    assert state.dead_letter_keys == ["match-001:btts"]
    assert state.retry_queue == ["match-001:btts"]
    assert any(event.get("status") == "dead_letter" for event in worker.state_store.events())


def test_stale_and_late_events_are_skipped_without_prediction(tmp_path: Path) -> None:
    stale = WorkerEvent(
        match_id="stale",
        market="cards",
        kickoff_utc=NOW + timedelta(hours=2),
        observed_at_utc=NOW - timedelta(days=2),
        source_version="fixture-v1",
    )
    late = _event(match_id="late", kickoff=NOW - timedelta(minutes=1))
    worker = _worker(
        tmp_path,
        source=lambda *, as_of_utc: [stale, late],
        config_overrides={"stale_after_seconds": 60.0},
    )
    result = worker.run_once(as_of_utc=NOW)
    assert result.status == "partial_data"
    assert result.skipped_events == 2
    assert result.predictions_issued == 0
    event_names = [event["event"] for event in worker.state_store.events()]
    assert "stale_data_skipped" in event_names
    assert "late_event_skipped" in event_names


def test_no_data_and_partial_data_are_explicit(tmp_path: Path) -> None:
    no_data = _worker(tmp_path / "no-data", source=lambda *, as_of_utc: [])
    assert no_data.run_once(as_of_utc=NOW).status == "no_data"

    partial = _worker(
        tmp_path / "partial",
        source=lambda *, as_of_utc: [
            _event(),
            _event(match_id="late", kickoff=NOW - timedelta(seconds=1)),
        ],
    )
    result = partial.run_once(as_of_utc=NOW)
    assert result.status == "partial_data"
    assert result.predictions_issued == 1
    assert result.skipped_events == 1


def test_source_timeout_and_circuit_breaker(tmp_path: Path) -> None:
    def slow_source(*, as_of_utc: datetime) -> list[WorkerEvent]:
        time.sleep(0.05)
        return [_event()]

    worker = _worker(
        tmp_path,
        source=slow_source,
        config_overrides={
            "source_timeout_seconds": 0.001,
            "circuit_failure_threshold": 2,
            "circuit_cooldown_seconds": 60.0,
        },
    )
    first = worker.run_once(as_of_utc=NOW)
    second = worker.run_once(as_of_utc=NOW)
    third = worker.run_once(as_of_utc=NOW)
    assert first.status == "source_failed"
    assert second.status == "source_failed"
    assert third.status == "source_circuit_open"
    assert isinstance(worker.state_store.load().source_circuit_open_until_utc, str)


def test_prediction_timeout_is_recorded_and_retried(tmp_path: Path) -> None:
    def slow_predictor(event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
        time.sleep(0.05)
        return _predictor(event, as_of_utc=as_of_utc)

    worker = _worker(
        tmp_path,
        predictor=slow_predictor,
        config_overrides={"source_timeout_seconds": 0.001},
    )
    result = worker.run_once(as_of_utc=NOW)
    assert result.status == "partial_data"
    assert worker.state_store.load().retry_queue == ["match-001:btts"]
    assert any(event["event"] == "prediction_failed" for event in worker.state_store.events())


def test_crash_recovery_reprocesses_in_progress_event(tmp_path: Path) -> None:
    crashed_event = _event(match_id="match-crashed")
    worker = _worker(tmp_path, source=lambda *, as_of_utc: [crashed_event])
    worker.state_store.save(
        worker.state_store.load().model_copy(
            update={"current_event_key": "match-crashed:btts", "current_phase": "prediction"}
        )
    )
    result = worker.run_once(as_of_utc=NOW)
    state = worker.state_store.load()
    assert result.predictions_issued == 1
    assert state.restart_recoveries == 1
    assert state.processed_event_keys == ["match-crashed:btts"]
    assert any(event["event"] == "startup_recovery" for event in worker.state_store.events())


def test_keyboard_interrupt_leaves_recovery_marker_and_next_worker_recovers(
    tmp_path: Path,
) -> None:
    def crashing_predictor(event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
        raise KeyboardInterrupt("simulated process crash")

    crashed = _worker(
        tmp_path,
        predictor=crashing_predictor,
        source=lambda *, as_of_utc: [_event(match_id="restart-me")],
    )
    with pytest.raises(KeyboardInterrupt):
        crashed.run_once(as_of_utc=NOW)
    persisted = crashed.state_store.load()
    assert persisted.current_event_key == "restart-me:btts"
    recovered = _worker(
        tmp_path,
        source=lambda *, as_of_utc: [_event(match_id="restart-me")],
    )
    result = recovered.run_once(as_of_utc=NOW)
    assert result.predictions_issued == 1
    assert recovered.state_store.load().restart_recoveries == 1


def test_file_lock_prevents_duplicate_worker(tmp_path: Path) -> None:
    path = tmp_path / "worker.lock"
    first = FileLock(path)
    second = FileLock(path)
    first.acquire()
    try:
        with pytest.raises(WorkerAlreadyRunning):
            second.acquire()
    finally:
        first.release()
    assert not path.exists()


def test_run_forever_honors_iteration_bound_and_graceful_shutdown(tmp_path: Path) -> None:
    worker = _worker(tmp_path, config_overrides={"polling_interval_seconds": 0.0})
    worker.run_forever(max_iterations=2)
    state = worker.state_store.load()
    assert state.iteration == 2
    assert state.status == "stopped"
    assert sum(event["event"] == "heartbeat" for event in worker.state_store.events()) == 2
    assert any(event["event"] == "graceful_shutdown" for event in worker.state_store.events())


def test_stop_event_allows_graceful_exit(tmp_path: Path) -> None:
    worker = _worker(tmp_path, config_overrides={"polling_interval_seconds": 0.0})
    worker.request_stop()
    worker.run_forever(max_iterations=2)
    assert worker.state_store.load().status == "stopped"


def test_worker_contracts_reject_labels_financial_fields_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        WorkerEvent.model_validate({**_event().model_dump(), "target": 1})
    with pytest.raises(ValidationError):
        WorkerPrediction.model_validate(
            {**_predictor(_event(), as_of_utc=NOW).model_dump(), "result": "x"}
        )
    with pytest.raises(ValidationError):
        WorkerEvent(
            match_id="x",
            market="btts",
            kickoff_utc="2025-01-01T13:00:00",
            observed_at_utc=NOW,
            source_version="v1",
        )


def test_state_json_is_canonical_and_contains_no_sensitive_fields(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    worker.run_once(as_of_utc=NOW)
    raw = (tmp_path / "worker" / "state.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    payload = json.loads(raw)
    assert list(payload) == sorted(payload)
    forbidden = {"target", "result", "odds", "roi", "ev", "stake"}
    assert not forbidden.intersection(payload)
