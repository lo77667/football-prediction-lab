"""Safe, local-only Telegram notification adapter for Cycle 43."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from football_prediction_lab.service.contracts import ShadowPrediction

MAX_TELEGRAM_MESSAGE_LENGTH = 4096
FORBIDDEN_MESSAGE_TERMS = {
    "target",
    "result",
    "odds",
    "roi",
    "ev",
    "stake",
    "home_goals",
    "away_goals",
    "raw_csv",
    "source_uri",
}
MARKDOWN_V2_SPECIALS = r"_[]()~`>#+-=|{}.\\!"


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def escape_markdown_v2(value: str) -> str:
    """Escape Telegram MarkdownV2 syntax without interpreting user-controlled text."""

    escaped: list[str] = []
    for character in value:
        if character in MARKDOWN_V2_SPECIALS:
            escaped.append("\\")
        escaped.append(character)
    return "".join(escaped)


def _safe_error_text(value: str) -> str:
    """Return bounded error text with tokens, auth headers, and local paths removed."""

    safe = re.sub(
        r"(?i)(bearer\s+|bot\d+:[a-z0-9_-]+|token\s*[=:]\s*)[^\s,;]+", "[redacted]", value
    )
    safe = re.sub(r"/(?:home|tmp|var|etc)/[^\s]+", "[path-redacted]", safe)
    safe = re.sub(r"[\r\n\t]+", " ", safe)
    return safe[:256]


def _contains_forbidden_terms(value: str) -> list[str]:
    lowered = value.lower()
    return sorted(
        term for term in FORBIDDEN_MESSAGE_TERMS if re.search(rf"\b{re.escape(term)}\b", lowered)
    )


class TelegramAdapterError(RuntimeError):
    """Base error for safe local notification operations."""


class ProductionDisabledError(TelegramAdapterError):
    """Raised whenever real Telegram production delivery is requested."""


class NotificationContractError(TelegramAdapterError):
    """Raised when a signal cannot be represented safely as a notification."""


class TelegramRequestError(TelegramAdapterError):
    """Controlled fake-client transport error with retry classification."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(_safe_error_text(message))


class TelegramClient(Protocol):
    def send_message(self, *, chat_id: str, text: str) -> str:
        """Send a safe message and return a non-sensitive fake/message identifier."""


class NotificationSignal(BaseModel):
    """Minimal pre-match signal contract; no targets, raw data, or financial fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market: str = Field(min_length=1, max_length=64)
    match_id: str = Field(min_length=1, max_length=128)
    kickoff_utc: datetime
    probability: float = Field(ge=0.0, le=1.0)
    model_version: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    issued_at_utc: datetime
    disclaimer: str = Field(min_length=1, max_length=512)

    @field_validator("market", "match_id", "model_version", "policy_version", "disclaimer")
    @classmethod
    def reject_unsafe_text(cls, value: str) -> str:
        if _contains_forbidden_terms(value):
            raise ValueError("notification text contains a forbidden term")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("notification text contains a control character")
        return value

    @classmethod
    def from_prediction(cls, prediction: ShadowPrediction) -> NotificationSignal:
        return cls(
            market=prediction.market,
            match_id=prediction.match_id,
            kickoff_utc=prediction.kickoff_utc,
            probability=prediction.probability,
            model_version=prediction.model_version,
            policy_version=prediction.policy_version,
            issued_at_utc=prediction.issued_at_utc,
            disclaimer="معلومة pre-match غير مضمونة وليست توصية مالية.",
        )


class TelegramMessage(BaseModel):
    """Rendered message contract with a deterministic notification identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    notification_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    chat_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=MAX_TELEGRAM_MESSAGE_LENGTH)
    parse_mode: Literal["MarkdownV2"] = "MarkdownV2"

    @field_validator("chat_id")
    @classmethod
    def validate_chat_id(cls, value: str) -> str:
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("chat_id contains a control character")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if _contains_forbidden_terms(value):
            raise ValueError("message contains forbidden terms")
        if "api_key" in value.lower() or "authorization" in value.lower():
            raise ValueError("message contains sensitive terms")
        return value


class NotificationPolicy(BaseModel):
    """Explicit notification policy; disabled and shadow-only by default."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    allowed_markets: frozenset[str] = frozenset({"btts", "cards"})
    require_pre_match: bool = True
    production_enabled: bool = False

    def permits(self, signal: NotificationSignal, *, mode: str) -> bool:
        if not self.enabled or self.production_enabled or mode == "production":
            return False
        if signal.market not in self.allowed_markets:
            return False
        if self.require_pre_match and signal.kickoff_utc <= signal.issued_at_utc:
            return False
        return True


class TelegramAdapterConfig(BaseModel):
    """Runtime settings with production delivery hard-disabled by default."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["dry_run", "test", "production"] = "dry_run"
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_base_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    message_length_limit: int = Field(
        default=MAX_TELEGRAM_MESSAGE_LENGTH, ge=128, le=MAX_TELEGRAM_MESSAGE_LENGTH
    )


@dataclass(frozen=True)
class NotificationOutcome:
    notification_id: str
    status: str
    attempts: int
    retryable: bool = False
    error_code: str | None = None
    message_id: str | None = None


class NotificationLedger:
    """Append-only notification ledger independent from the prediction ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        safe_event = dict(event)
        safe_event.pop("bot_token", None)
        safe_event.pop("authorization", None)
        safe_event.pop("text", None)
        safe_event.pop("raw_data", None)
        line = _canonical_json(safe_event)
        with self.path.open("ab") as handle:
            handle.write(line)

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def latest(self, notification_id: str) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        for event in self.events():
            if event.get("notification_id") == notification_id:
                latest = event
        return latest


class FakeTelegramClient:
    """Deterministic test client; it never opens a socket or contacts Telegram."""

    def __init__(self, outcomes: list[str | Exception] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.sent: list[dict[str, str]] = []
        self.calls = 0

    def send_message(self, *, chat_id: str, text: str) -> str:
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            message_id = str(outcome)
        else:
            message_id = f"fake-message-{self.calls}"
        self.sent.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        return message_id


def notification_id(signal: NotificationSignal, *, chat_id: str) -> str:
    semantic = {"chat_id": chat_id, **signal.model_dump(mode="json")}
    return _sha256(_canonical_json(semantic))


def render_message(
    signal: NotificationSignal, *, chat_id: str, length_limit: int
) -> TelegramMessage:
    identifier = notification_id(signal, chat_id=chat_id)
    fields = {
        "market": escape_markdown_v2(signal.market),
        "match_id": escape_markdown_v2(signal.match_id),
        "kickoff": escape_markdown_v2(signal.kickoff_utc.isoformat()),
        "probability": escape_markdown_v2(f"{signal.probability:.2%}"),
        "model": escape_markdown_v2(signal.model_version),
        "policy": escape_markdown_v2(signal.policy_version),
        "issued": escape_markdown_v2(signal.issued_at_utc.isoformat()),
        "disclaimer": escape_markdown_v2(signal.disclaimer),
    }
    text = (
        "*إشارة pre\\-match معلوماتية*\n"
        f"السوق: `{fields['market']}`\n"
        f"المباراة: `{fields['match_id']}`\n"
        f"موعد البداية UTC: `{fields['kickoff']}`\n"
        f"الاحتمال: `{fields['probability']}`\n"
        f"النموذج: `{fields['model']}`\n"
        f"السياسة: `{fields['policy']}`\n"
        f"وقت الإصدار UTC: `{fields['issued']}`\n\n"
        f"_{fields['disclaimer']}_"
    )
    if len(text) > length_limit:
        raise NotificationContractError("rendered message exceeds the configured length limit")
    return TelegramMessage(notification_id=identifier, chat_id=chat_id, text=text)


class TelegramAdapter:
    """Separate notification adapter with dry-run/test modes and no real transport."""

    def __init__(
        self,
        *,
        ledger: NotificationLedger,
        policy: NotificationPolicy | None = None,
        config: TelegramAdapterConfig | None = None,
        client: TelegramClient | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ledger = ledger
        self.policy = policy or NotificationPolicy()
        self.config = config or TelegramAdapterConfig()
        self.client = client
        self.sleep_fn = sleep_fn
        if self.config.mode == "production" or self.policy.production_enabled:
            raise ProductionDisabledError(
                "real Telegram production delivery is disabled in Cycle 43"
            )
        if self.config.mode == "test" and client is None:
            raise TelegramAdapterError("test mode requires an injected fake client")

    def prepare(self, signal: NotificationSignal, *, chat_id: str) -> TelegramMessage:
        if not self.policy.permits(signal, mode=self.config.mode):
            raise NotificationContractError("notification policy does not permit this signal")
        try:
            return render_message(
                signal, chat_id=chat_id, length_limit=self.config.message_length_limit
            )
        except ValueError as error:
            raise NotificationContractError(_safe_error_text(str(error))) from error

    def send(self, signal: NotificationSignal, *, chat_id: str) -> NotificationOutcome:
        message = self.prepare(signal, chat_id=chat_id)
        previous = self.ledger.latest(message.notification_id)
        if previous and previous.get("status") in {"sent", "dry_run"}:
            return NotificationOutcome(
                notification_id=message.notification_id,
                status="duplicate_skipped",
                attempts=int(previous.get("attempt", 0)),
                message_id=previous.get("message_id"),
            )
        if self.config.mode == "dry_run":
            self.ledger.append(
                {
                    "event": "notification_dry_run",
                    "notification_id": message.notification_id,
                    "attempt": 0,
                    "status": "dry_run",
                    "commercial_release": False,
                }
            )
            return NotificationOutcome(message.notification_id, "dry_run", 0)
        if self.client is None:
            raise TelegramAdapterError("test client is required when production is disabled")

        for attempt in range(1, self.config.max_attempts + 1):
            self.ledger.append(
                {
                    "event": "notification_attempt",
                    "notification_id": message.notification_id,
                    "attempt": attempt,
                    "status": "attempt_started",
                    "commercial_release": False,
                }
            )
            try:
                message_id = self.client.send_message(chat_id=message.chat_id, text=message.text)
            except TelegramRequestError as error:
                status = (
                    "retryable_failed"
                    if error.retryable and attempt < self.config.max_attempts
                    else "dead_letter"
                )
                self.ledger.append(
                    {
                        "event": "notification_failed",
                        "notification_id": message.notification_id,
                        "attempt": attempt,
                        "status": status,
                        "error_code": error.code,
                        "error_message": _safe_error_text(str(error)),
                        "retryable": error.retryable,
                        "commercial_release": False,
                    }
                )
                if not error.retryable:
                    return NotificationOutcome(
                        message.notification_id, "dead_letter", attempt, False, error.code
                    )
                if attempt == self.config.max_attempts:
                    return NotificationOutcome(
                        message.notification_id, "dead_letter", attempt, True, error.code
                    )
                self.sleep_fn(self.config.backoff_base_seconds * (2 ** (attempt - 1)))
                continue
            except Exception as error:  # pragma: no cover - defensive boundary
                safe_message = _safe_error_text(str(error))
                self.ledger.append(
                    {
                        "event": "notification_failed",
                        "notification_id": message.notification_id,
                        "attempt": attempt,
                        "status": "dead_letter",
                        "error_code": "unexpected_client_error",
                        "error_message": safe_message,
                        "retryable": False,
                        "commercial_release": False,
                    }
                )
                return NotificationOutcome(
                    message.notification_id,
                    "dead_letter",
                    attempt,
                    False,
                    "unexpected_client_error",
                )
            self.ledger.append(
                {
                    "event": "notification_sent",
                    "notification_id": message.notification_id,
                    "attempt": attempt,
                    "status": "sent",
                    "message_id": _safe_error_text(message_id),
                    "commercial_release": False,
                }
            )
            return NotificationOutcome(
                message.notification_id, "sent", attempt, message_id=_safe_error_text(message_id)
            )
        raise AssertionError("notification retry loop exhausted unexpectedly")
