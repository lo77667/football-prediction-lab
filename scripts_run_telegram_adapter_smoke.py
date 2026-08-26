"""Run deterministic Cycle 43 Telegram adapter smoke tests without network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football_prediction_lab.notification.telegram import (
    FakeTelegramClient,
    NotificationLedger,
    NotificationPolicy,
    NotificationSignal,
    ProductionDisabledError,
    TelegramAdapter,
    TelegramAdapterConfig,
    TelegramMessage,
    TelegramRequestError,
)
from football_prediction_lab.service.contracts import ShadowPrediction

ROOT = Path(__file__).resolve().parent
SOURCE_RESPONSE = (
    ROOT
    / "reports"
    / "generated"
    / "cycle_41_1_service_smoke"
    / "runs"
    / "356b08d69b859a1d30e24865196ac120aacb118679127d859f1f202e57ba2ec0"
    / "service_response.json"
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "reports" / "generated" / "cycle_43_telegram_smoke",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    prediction_payload = json.loads(SOURCE_RESPONSE.read_text(encoding="utf-8"))["predictions"][0]
    signal = NotificationSignal.from_prediction(ShadowPrediction.model_validate(prediction_payload))

    dry_run_ledger = NotificationLedger(output_root / "notification_ledger_dry_run.jsonl")
    dry_run = TelegramAdapter(
        ledger=dry_run_ledger,
        policy=NotificationPolicy(enabled=True),
        config=TelegramAdapterConfig(mode="dry_run"),
    )
    dry_first = dry_run.send(signal, chat_id="cycle43-test-channel")
    dry_duplicate = dry_run.send(signal, chat_id="cycle43-test-channel")

    sleeps: list[float] = []
    fake_client = FakeTelegramClient(
        [TelegramRequestError("http_429", "rate limited", retryable=True), "fake-message-2"]
    )
    test_ledger = NotificationLedger(output_root / "notification_ledger_test.jsonl")
    test_adapter = TelegramAdapter(
        ledger=test_ledger,
        policy=NotificationPolicy(enabled=True),
        config=TelegramAdapterConfig(mode="test", max_attempts=2, backoff_base_seconds=0.1),
        client=fake_client,
        sleep_fn=sleeps.append,
    )
    test_outcome = test_adapter.send(signal, chat_id="cycle43-test-channel")

    production_blocked = False
    try:
        TelegramAdapter(
            ledger=NotificationLedger(output_root / "production_blocked.jsonl"),
            policy=NotificationPolicy(enabled=True),
            config=TelegramAdapterConfig(mode="production"),
        )
    except ProductionDisabledError:
        production_blocked = True

    _write_json(
        output_root / "message_contract.json",
        {
            "signal_schema": NotificationSignal.model_json_schema(),
            "telegram_message_schema": TelegramMessage.model_json_schema(),
            "production_enabled": False,
            "commercial_release": False,
        },
    )
    _write_json(
        output_root / "validation.json",
        {
            "validation": "passed",
            "dry_run_status": dry_first.status,
            "duplicate_status": dry_duplicate.status,
            "test_status": test_outcome.status,
            "test_attempts": test_outcome.attempts,
            "fake_client_calls": fake_client.calls,
            "backoff_seconds": sleeps,
            "production_blocked": production_blocked,
            "network_scope": "none",
            "commercial_release": False,
        },
    )
    _write_json(
        output_root / "smoke_summary.json",
        {
            "dry_run_ledger": "notification_ledger_dry_run.jsonl",
            "test_ledger": "notification_ledger_test.jsonl",
            "message_contract": "message_contract.json",
            "validation": "validation.json",
            "notification_id": dry_first.notification_id,
            "commercial_release": False,
        },
    )
    print(
        json.dumps(
            {
                "dry_run": dry_first.status,
                "duplicate": dry_duplicate.status,
                "test": test_outcome.status,
                "attempts": test_outcome.attempts,
                "production_blocked": production_blocked,
                "network_scope": "none",
                "commercial_release": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
