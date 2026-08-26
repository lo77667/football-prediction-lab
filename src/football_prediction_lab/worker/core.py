"""Deterministic local worker primitives for Cycle 44.

The worker is callback-driven so the default implementation can run entirely on
local fixtures. No callback opens a network connection by itself; callers must
inject explicitly tested local components.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkerMode = Literal["dry-run", "shadow", "telegram-disabled"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("worker timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class WorkerError(RuntimeError):
    """Base worker error."""


class WorkerAlreadyRunning(WorkerError):
    """Raised when another worker owns the same lock."""


class WorkerTimeout(WorkerError):
    """Raised when an injected source or notifier exceeds its timeout."""


class WorkerCallbackError(WorkerError):
    """Raised for controlled callback failures."""


class WorkerEvent(BaseModel):
    """Local normalized pre-match event; no labels or financial fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    match_id: str = Field(min_length=1, max_length=128)
    market: Literal["btts", "cards"]
    kickoff_utc: datetime
    observed_at_utc: datetime
    source_version: str = Field(min_length=1, max_length=128)

    @field_validator("kickoff_utc", "observed_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("worker timestamps must be timezone-aware")
        return value


class WorkerPrediction(BaseModel):
    """Prelabel worker output contract; no target, result, or financial fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction_id: str = Field(min_length=1, max_length=256)
    match_id: str = Field(min_length=1, max_length=128)
    market: Literal["btts", "cards"]
    kickoff_utc: datetime
    as_of_utc: datetime
    probability: float = Field(ge=0.0, le=1.0)
    model_version: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    feature_version: str = Field(min_length=1, max_length=128)

    @field_validator("kickoff_utc", "as_of_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("worker timestamps must be timezone-aware")
        return value


class WorkerConfig(BaseModel):
    """Bounded worker settings suitable for a local dry-run/shadow process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: WorkerMode = "dry-run"
    polling_interval_seconds: float = Field(default=60.0, ge=0.0, le=86_400.0)
    source_timeout_seconds: float = Field(default=5.0, gt=0.0, le=300.0)
    notification_timeout_seconds: float = Field(default=5.0, gt=0.0, le=300.0)
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_base_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    stale_after_seconds: float = Field(default=86_400.0, gt=0.0, le=604_800.0)
    circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    circuit_cooldown_seconds: float = Field(default=300.0, ge=0.0, le=86_400.0)


class WorkerState(BaseModel):
    """Persisted state; lists are bounded by the worker's dedup policy."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "cycle44-worker-state-v1"
    status: str = "created"
    last_heartbeat_utc: str | None = None
    current_event_key: str | None = None
    current_phase: str | None = None
    processed_event_keys: list[str] = Field(default_factory=list)
    prediction_keys: list[str] = Field(default_factory=list)
    notification_keys: list[str] = Field(default_factory=list)
    retry_queue: list[str] = Field(default_factory=list)
    dead_letter_keys: list[str] = Field(default_factory=list)
    source_failures: int = 0
    notification_failures: int = 0
    source_circuit_open_until_utc: str | None = None
    notification_circuit_open_until_utc: str | None = None
    restart_recoveries: int = 0
    iteration: int = 0


class StateStore:
    """Atomic JSON state plus append-only operational event log."""

    def __init__(self, state_path: Path, events_path: Path | None = None) -> None:
        self.state_path = state_path
        self.events_path = events_path or state_path.with_suffix(".events.jsonl")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> WorkerState:
        if not self.state_path.exists():
            return WorkerState()
        return WorkerState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def save(self, state: WorkerState) -> None:
        temporary = self.state_path.with_name(f".{self.state_path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(_canonical(state.model_dump(mode="json")))
        os.replace(temporary, self.state_path)

    def append_event(self, event: dict[str, Any]) -> None:
        with self.events_path.open("ab") as handle:
            handle.write(_canonical(event))

    def events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class FileLock:
    """Cross-process lock using atomic file creation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise WorkerAlreadyRunning("worker lock is already held") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        self._held = True

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()


class EventSource(Protocol):
    def __call__(self, *, as_of_utc: datetime) -> list[WorkerEvent]:
        """Return normalized local events or raise a controlled error."""


class Predictor(Protocol):
    def __call__(self, event: WorkerEvent, *, as_of_utc: datetime) -> WorkerPrediction:
        """Produce one prelabel prediction without reading a label."""


class Notifier(Protocol):
    def __call__(self, prediction: WorkerPrediction) -> str:
        """Deliver via an explicitly injected dry-run/test notifier."""


@dataclass(frozen=True)
class WorkerCycleResult:
    status: str
    iteration: int
    as_of_utc: str
    accepted_events: int = 0
    skipped_events: int = 0
    predictions_issued: int = 0
    notifications_sent: int = 0
    failures: int = 0


class LocalWorker:
    """Crash-recoverable local worker with bounded, deterministic lifecycle."""

    def __init__(
        self,
        *,
        state_store: StateStore,
        lock: FileLock,
        config: WorkerConfig,
        source: EventSource,
        predictor: Predictor,
        notifier: Notifier | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if config.mode != "telegram-disabled" and notifier is None and config.mode != "dry-run":
            raise WorkerError("shadow mode requires an explicitly injected notifier")
        self.state_store = state_store
        self.lock = lock
        self.config = config
        self.source = source
        self.predictor = predictor
        self.notifier = notifier
        self.sleep_fn = sleep_fn
        self.clock = clock
        self.stop_event = threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def _state(self) -> WorkerState:
        return self.state_store.load()

    def _save_event(self, state: WorkerState, event: dict[str, Any]) -> None:
        self.state_store.append_event({"commercial_release": False, **event})
        self.state_store.save(state)

    def _heartbeat(self, state: WorkerState, now: datetime) -> None:
        state.last_heartbeat_utc = _iso(now)
        state.status = "running"
        self.state_store.save(state)
        self.state_store.append_event(
            {"event": "heartbeat", "as_of_utc": _iso(now), "commercial_release": False}
        )

    def _call_with_timeout(self, callback: Callable[[], Any], timeout: float, label: str) -> Any:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"cycle44-{label}")
        future = executor.submit(callback)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as error:
            future.cancel()
            raise WorkerTimeout(f"{label} callback exceeded timeout") from error
        except Exception as error:
            raise WorkerCallbackError(f"{label} callback failed") from error
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _circuit_open(self, until: str | None, now: datetime) -> bool:
        if not until:
            return False
        return datetime.fromisoformat(until) > now

    def _open_source_circuit(self, state: WorkerState, now: datetime) -> None:
        state.source_circuit_open_until_utc = _iso(
            now + timedelta(seconds=self.config.circuit_cooldown_seconds)
        )

    def _open_notification_circuit(self, state: WorkerState, now: datetime) -> None:
        state.notification_circuit_open_until_utc = _iso(
            now + timedelta(seconds=self.config.circuit_cooldown_seconds)
        )

    def _event_key(self, event: WorkerEvent) -> str:
        return f"{event.match_id}:{event.market}"

    def _retry_notification(
        self, state: WorkerState, prediction: WorkerPrediction, now: datetime
    ) -> tuple[bool, int]:
        if self.config.mode == "telegram-disabled":
            self.state_store.append_event(
                {
                    "event": "notification_skipped",
                    "prediction_id": prediction.prediction_id,
                    "reason": "telegram_disabled",
                    "commercial_release": False,
                }
            )
            return True, 0
        if self.config.mode == "dry-run":
            self.state_store.append_event(
                {
                    "event": "notification_dry_run",
                    "prediction_id": prediction.prediction_id,
                    "commercial_release": False,
                }
            )
            return True, 0
        if self.notifier is None:
            return False, 0
        if self._circuit_open(state.notification_circuit_open_until_utc, now):
            self.state_store.append_event(
                {
                    "event": "notification_circuit_open",
                    "prediction_id": prediction.prediction_id,
                    "commercial_release": False,
                }
            )
            return False, 0
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                message_id = self._call_with_timeout(
                    lambda: self.notifier(prediction),
                    self.config.notification_timeout_seconds,
                    "notification",
                )
            except WorkerError:
                state.notification_failures += 1
                if state.notification_failures >= self.config.circuit_failure_threshold:
                    self._open_notification_circuit(state, now)
                final = attempt == self.config.max_attempts
                self.state_store.append_event(
                    {
                        "event": "notification_failed",
                        "prediction_id": prediction.prediction_id,
                        "attempt": attempt,
                        "status": "dead_letter" if final else "retryable_failed",
                        "error_code": "notification_failure",
                        "retryable": not final,
                        "commercial_release": False,
                    }
                )
                if not final:
                    self.sleep_fn(self.config.backoff_base_seconds * (2 ** (attempt - 1)))
                continue
            state.notification_failures = 0
            state.notification_circuit_open_until_utc = None
            self.state_store.append_event(
                {
                    "event": "notification_sent",
                    "prediction_id": prediction.prediction_id,
                    "attempt": attempt,
                    "message_id": str(message_id)[:128],
                    "commercial_release": False,
                }
            )
            return True, attempt
        state.dead_letter_keys.append(prediction.prediction_id)
        return False, self.config.max_attempts

    def _recover_startup(self, state: WorkerState, now: datetime) -> None:
        if state.current_event_key is None:
            return
        state.restart_recoveries += 1
        self.state_store.append_event(
            {
                "event": "startup_recovery",
                "event_key": state.current_event_key,
                "previous_phase": state.current_phase,
                "as_of_utc": _iso(now),
                "commercial_release": False,
            }
        )
        state.retry_queue = sorted(set(state.retry_queue + [state.current_event_key]))
        state.current_event_key = None
        state.current_phase = None
        self.state_store.save(state)

    def run_once(self, *, as_of_utc: datetime | None = None) -> WorkerCycleResult:
        now = as_of_utc or self.clock()
        if now.tzinfo is None:
            raise ValueError("as_of_utc must be timezone-aware")
        with self.lock:
            state = self._state()
            self._recover_startup(state, now)
            state.iteration += 1
            self._heartbeat(state, now)
            if self._circuit_open(state.source_circuit_open_until_utc, now):
                state.status = "source_circuit_open"
                self.state_store.save(state)
                return WorkerCycleResult("source_circuit_open", state.iteration, _iso(now))
            try:
                events = self._call_with_timeout(
                    lambda: self.source(as_of_utc=now),
                    self.config.source_timeout_seconds,
                    "source",
                )
            except WorkerError:
                state.source_failures += 1
                if state.source_failures >= self.config.circuit_failure_threshold:
                    self._open_source_circuit(state, now)
                self._save_event(
                    state,
                    {
                        "event": "source_failed",
                        "as_of_utc": _iso(now),
                        "error_code": "source_failure",
                    },
                )
                return WorkerCycleResult("source_failed", state.iteration, _iso(now), failures=1)
            state.source_failures = 0
            state.source_circuit_open_until_utc = None
            if not events:
                state.status = "no_data"
                self._save_event(state, {"event": "no_data", "as_of_utc": _iso(now)})
                return WorkerCycleResult("no_data", state.iteration, _iso(now))

            accepted = 0
            skipped = 0
            issued = 0
            sent = 0
            failures = 0
            for event in events:
                event_key = self._event_key(event)
                if event_key in state.processed_event_keys:
                    skipped += 1
                    self.state_store.append_event(
                        {
                            "event": "duplicate_skipped",
                            "event_key": event_key,
                            "commercial_release": False,
                        }
                    )
                    continue
                if now - event.observed_at_utc > timedelta(seconds=self.config.stale_after_seconds):
                    skipped += 1
                    self.state_store.append_event(
                        {
                            "event": "stale_data_skipped",
                            "event_key": event_key,
                            "commercial_release": False,
                        }
                    )
                    continue
                if event.kickoff_utc <= now:
                    skipped += 1
                    self.state_store.append_event(
                        {
                            "event": "late_event_skipped",
                            "event_key": event_key,
                            "commercial_release": False,
                        }
                    )
                    continue
                accepted += 1
                state.current_event_key = event_key
                state.current_phase = "prediction"
                self.state_store.save(state)
                try:
                    prediction = self._call_with_timeout(
                        lambda event=event: self.predictor(event, as_of_utc=now),
                        self.config.source_timeout_seconds,
                        "prediction",
                    )
                except WorkerError:
                    failures += 1
                    state.retry_queue.append(event_key)
                    self.state_store.append_event(
                        {
                            "event": "prediction_failed",
                            "event_key": event_key,
                            "error_code": "prediction_failure",
                            "commercial_release": False,
                        }
                    )
                    state.current_event_key = None
                    state.current_phase = None
                    self.state_store.save(state)
                    continue
                if prediction.kickoff_utc <= prediction.as_of_utc:
                    failures += 1
                    self.state_store.append_event(
                        {
                            "event": "prediction_rejected",
                            "event_key": event_key,
                            "reason": "prediction_after_kickoff_guard",
                            "commercial_release": False,
                        }
                    )
                    state.processed_event_keys.append(event_key)
                    state.current_event_key = None
                    state.current_phase = None
                    self.state_store.save(state)
                    continue
                issued += 1
                state.prediction_keys.append(prediction.prediction_id)
                self.state_store.append_event(
                    {
                        "event": "prediction_issued",
                        "prediction_id": prediction.prediction_id,
                        "event_key": event_key,
                        "as_of_utc": _iso(now),
                        "commercial_release": False,
                    }
                )
                state.current_phase = "notification"
                state.notification_keys = sorted(set(state.notification_keys))
                notified, _ = self._retry_notification(state, prediction, now)
                if notified:
                    sent += 1
                    state.notification_keys.append(prediction.prediction_id)
                    state.retry_queue = [key for key in state.retry_queue if key != event_key]
                    state.processed_event_keys.append(event_key)
                else:
                    failures += 1
                    state.retry_queue.append(event_key)
                state.current_event_key = None
                state.current_phase = None
                self.state_store.save(state)
            state.status = "partial_data" if failures or skipped else "completed"
            state.processed_event_keys = sorted(set(state.processed_event_keys))
            state.prediction_keys = sorted(set(state.prediction_keys))
            state.notification_keys = sorted(set(state.notification_keys))
            self._save_event(
                state,
                {
                    "event": "cycle_completed",
                    "status": state.status,
                    "accepted_events": accepted,
                    "skipped_events": skipped,
                    "predictions_issued": issued,
                    "notifications_sent": sent,
                    "failures": failures,
                    "as_of_utc": _iso(now),
                },
            )
            return WorkerCycleResult(
                state.status, state.iteration, _iso(now), accepted, skipped, issued, sent, failures
            )

    def run_forever(self, *, max_iterations: int | None = None) -> None:
        with self.lock:
            self._run_forever_locked(max_iterations=max_iterations)

    def _run_forever_locked(self, *, max_iterations: int | None) -> None:
        iterations = 0
        while not self.stop_event.is_set() and (
            max_iterations is None or iterations < max_iterations
        ):
            # run_once has its own lock boundary; this loop uses an internal cycle method
            self.lock.release()
            try:
                self.run_once()
            finally:
                self.lock.acquire()
            iterations += 1
            if not self.stop_event.is_set() and (
                max_iterations is None or iterations < max_iterations
            ):
                self.sleep_fn(self.config.polling_interval_seconds)
        state = self._state()
        state.status = "stopped"
        self.state_store.append_event({"event": "graceful_shutdown", "commercial_release": False})
        self.state_store.save(state)
