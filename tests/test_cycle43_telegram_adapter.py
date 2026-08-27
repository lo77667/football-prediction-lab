from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from football_prediction_lab.notification.telegram import (
    FakeTelegramClient,
    NotificationContractError,
    NotificationLedger,
    NotificationPolicy,
    NotificationSignal,
    ProductionDisabledError,
    TelegramAdapter,
    TelegramAdapterConfig,
    TelegramMessage,
    TelegramRequestError,
    render_message,
)
from football_prediction_lab.service.contracts import ShadowPrediction

ROOT = Path(__file__).resolve().parents[1]
RESPONSE_PATH = (
    ROOT
    / "reports"
    / "generated"
    / "cycle_41_1_service_smoke"
    / "runs"
    / "356b08d69b859a1d30e24865196ac120aacb118679127d859f1f202e57ba2ec0"
    / "service_response.json"
)


def _signal(**overrides: Any) -> NotificationSignal:
    payload: dict[str, Any] = {
        "market": "btts",
        "match_id": "match-001",
        "kickoff_utc": "2025-01-02T15:00:00Z",
        "probability": 0.62,
        "model_version": "cycle36-candidate-suite-v1",
        "policy_version": "cycle36-future-2627-policy-v1",
        "issued_at_utc": "2025-01-01T12:00:00Z",
        "disclaimer": "معلومة pre-match غير مضمونة وليست توصية مالية.",
    }
    payload.update(overrides)
    return NotificationSignal.model_validate(payload)


def _adapter(
    tmp_path: Path,
    *,
    mode: str = "dry_run",
    client: FakeTelegramClient | None = None,
    max_attempts: int = 3,
    backoff_base_seconds: float = 0.0,
    enabled: bool = True,
    sleep_fn: Any = lambda _: None,
) -> TelegramAdapter:
    return TelegramAdapter(
        ledger=NotificationLedger(tmp_path / "notification_ledger.jsonl"),
        policy=NotificationPolicy(enabled=enabled),
        config=TelegramAdapterConfig(
            mode=mode, max_attempts=max_attempts, backoff_base_seconds=backoff_base_seconds
        ),
        client=client,
        sleep_fn=sleep_fn,
    )


def test_dry_run_is_disabled_for_real_delivery_and_is_idempotent(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    first = adapter.send(_signal(), chat_id="test-chat")
    second = adapter.send(_signal(), chat_id="test-chat")
    assert first.status == "dry_run"
    assert second.status == "duplicate_skipped"
    assert first.notification_id == second.notification_id
    events = adapter.ledger.events()
    assert [event["status"] for event in events] == ["dry_run"]
    assert all("text" not in event for event in events)


def test_duplicate_is_skipped_after_adapter_restart(tmp_path: Path) -> None:
    first_client = FakeTelegramClient()
    first = _adapter(tmp_path, mode="test", client=first_client)
    assert first.send(_signal(), chat_id="test-chat").status == "sent"
    second_client = FakeTelegramClient()
    second = _adapter(tmp_path, mode="test", client=second_client)
    assert second.send(_signal(), chat_id="test-chat").status == "duplicate_skipped"
    assert second_client.calls == 0


def test_test_mode_fake_client_sends_once_and_duplicate_is_skipped(tmp_path: Path) -> None:
    client = FakeTelegramClient()
    adapter = _adapter(tmp_path, mode="test", client=client)
    first = adapter.send(_signal(), chat_id="test-chat")
    second = adapter.send(_signal(), chat_id="test-chat")
    assert first.status == "sent"
    assert first.attempts == 1
    assert second.status == "duplicate_skipped"
    assert client.calls == 1
    assert len(adapter.ledger.events()) == 2


def test_retryable_429_and_5xx_use_bounded_backoff(tmp_path: Path) -> None:
    client = FakeTelegramClient(
        [
            TelegramRequestError("http_429", "rate limited", retryable=True),
            TelegramRequestError("http_503", "temporary outage", retryable=True),
            "message-3",
        ]
    )
    sleeps: list[float] = []
    adapter = _adapter(
        tmp_path,
        mode="test",
        client=client,
        max_attempts=3,
        backoff_base_seconds=0.25,
        sleep_fn=sleeps.append,
    )
    outcome = adapter.send(_signal(), chat_id="test-chat")
    assert outcome.status == "sent"
    assert outcome.attempts == 3
    assert sleeps == [0.25, 0.5]
    statuses = [event["status"] for event in adapter.ledger.events()]
    assert statuses == [
        "attempt_started",
        "retryable_failed",
        "attempt_started",
        "retryable_failed",
        "attempt_started",
        "sent",
    ]


def test_permanent_error_goes_to_dead_letter_without_retry(tmp_path: Path) -> None:
    client = FakeTelegramClient(
        [TelegramRequestError("invalid_token", "token=bot123:secret-value", retryable=False)]
    )
    adapter = _adapter(tmp_path, mode="test", client=client)
    outcome = adapter.send(_signal(), chat_id="test-chat")
    assert outcome.status == "dead_letter"
    assert outcome.attempts == 1
    assert client.calls == 1
    content = (tmp_path / "notification_ledger.jsonl").read_text(encoding="utf-8")
    assert "secret-value" not in content
    assert "token=" not in content


def test_retry_exhaustion_is_dead_letter_and_bounded(tmp_path: Path) -> None:
    client = FakeTelegramClient(
        [
            TelegramRequestError("http_500", "temporary", retryable=True),
            TelegramRequestError("http_500", "temporary", retryable=True),
        ]
    )
    adapter = _adapter(tmp_path, mode="test", client=client, max_attempts=2)
    outcome = adapter.send(_signal(), chat_id="test-chat")
    assert outcome.status == "dead_letter"
    assert outcome.retryable is True
    assert outcome.attempts == 2
    assert client.calls == 2


def test_message_escaping_and_length_limit_are_enforced() -> None:
    message = render_message(_signal(match_id="A_[x]!"), chat_id="chat", length_limit=4096)
    assert "A\\_\\[x\\]\\!" in message.text
    assert message.parse_mode == "MarkdownV2"
    with pytest.raises(NotificationContractError, match="length"):
        render_message(_signal(), chat_id="chat", length_limit=128)


def test_pre_match_timing_guard_rejects_kickoff_at_or_before_issue_time(tmp_path: Path) -> None:
    with pytest.raises(NotificationContractError):
        _adapter(tmp_path).send(_signal(kickoff_utc="2025-01-01T11:00:00Z"), chat_id="test-chat")


@pytest.mark.parametrize(
    "field", ["target", "result", "odds", "roi", "ev", "stake", "raw_csv", "source_uri"]
)
def test_forbidden_signal_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        NotificationSignal.model_validate({**_signal().model_dump(), field: "blocked"})


def test_rendered_message_never_contains_odds_or_financial_fields() -> None:
    message = render_message(_signal(), chat_id="chat", length_limit=4096)
    lowered = message.text.lower()
    assert "odds" not in lowered
    assert "ev" not in lowered
    assert "roi" not in lowered
    assert "stake" not in lowered


def test_forbidden_terms_and_missing_chat_id_are_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationSignal.model_validate({**_signal().model_dump(), "match_id": "result-001"})
    with pytest.raises(ValidationError):
        render_message(_signal(), chat_id="\nchat", length_limit=4096)


def test_production_and_disabled_policy_cannot_send(tmp_path: Path) -> None:
    with pytest.raises(ProductionDisabledError):
        _adapter(tmp_path, mode="production")
    with pytest.raises(NotificationContractError):
        _adapter(tmp_path, enabled=False).send(_signal(), chat_id="test-chat")
    with pytest.raises(ProductionDisabledError):
        TelegramAdapter(
            ledger=NotificationLedger(tmp_path / "second.jsonl"),
            policy=NotificationPolicy(enabled=True, production_enabled=True),
            config=TelegramAdapterConfig(mode="test"),
            client=FakeTelegramClient(),
        )


def test_contract_is_frozen_and_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        NotificationSignal.model_validate({**_signal().model_dump(), "unexpected": 1})
    with pytest.raises(ValidationError):
        TelegramMessage.model_validate(
            {
                **render_message(_signal(), chat_id="chat", length_limit=4096).model_dump(),
                "target": 1,
            }
        )


def test_from_prediction_uses_only_prelabel_contract() -> None:
    payload = json.loads(RESPONSE_PATH.read_text(encoding="utf-8"))
    prediction = ShadowPrediction.model_validate(payload["predictions"][0])
    signal = NotificationSignal.from_prediction(prediction)
    assert signal.market == "btts"
    assert signal.match_id == prediction.match_id
    assert signal.probability == prediction.probability
    assert "result" not in signal.model_dump()


def test_ledger_filters_sensitive_fields_and_is_append_only(tmp_path: Path) -> None:
    ledger = NotificationLedger(tmp_path / "ledger.jsonl")
    ledger.append(
        {
            "event": "test",
            "notification_id": "a" * 64,
            "text": "sensitive raw message",
            "raw_data": {"target": 1},
            "bot_token": "bot123:secret",
            "authorization": "Bearer secret",
            "commercial_release": False,
        }
    )
    assert ledger.events() == [
        {"commercial_release": False, "event": "test", "notification_id": "a" * 64}
    ]


def test_signal_times_are_timezone_aware() -> None:
    signal = _signal()
    assert signal.kickoff_utc.tzinfo is not None
    assert signal.issued_at_utc.tzinfo is not None
    assert signal.kickoff_utc > signal.issued_at_utc
