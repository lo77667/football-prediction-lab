from __future__ import annotations

import copy
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from football_prediction_lab.ingestion.external_adapters import UnavailableExternalAdapter
from football_prediction_lab.ingestion.external_contracts import (
    ExternalSnapshotRecord,
    ExternalSource,
)
from football_prediction_lab.ingestion.external_readiness import (
    audit_snapshot_records,
    deferred_readiness_report,
    load_external_policy,
    write_readiness_report,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "cycle40_external_source_policy.yaml"


def _source(**overrides: object) -> ExternalSource:
    values: dict[str, object] = {
        "source_name": "authorized-test-feed",
        "provider": "test-provider",
        "endpoint_or_dataset_id": "dataset-test-v1",
        "source_version": "v1",
        "license_name": "test-only-authorized",
        "license_policy_reference": "tests-only",
        "allowed_reuse": False,
        "retrieved_at_utc": "2025-01-01T10:00:00Z",
        "available_at_utc": "2025-01-01T09:00:00Z",
        "request_or_snapshot_id": "snapshot-001",
        "input_sha256": "a" * 64,
        "schema_version": "external-test-v1",
        "retention_policy": "delete-after-test",
        "contact_owner": "test-owner",
    }
    values.update(overrides)
    return ExternalSource.model_validate(values)


def _record(**overrides: object) -> ExternalSnapshotRecord:
    values: dict[str, object] = {
        "source_name": "authorized-test-feed",
        "source_version": "v1",
        "request_or_snapshot_id": "snapshot-001",
        "snapshot_version": "snapshot-schema-v1",
        "input_sha256": "a" * 64,
        "match_id": "m-001",
        "kickoff_utc": "2025-01-01T15:00:00Z",
        "captured_at_utc": "2025-01-01T12:00:00Z",
        "available_at_utc": "2025-01-01T12:00:00Z",
    }
    values.update(overrides)
    return ExternalSnapshotRecord.model_validate(values)


def _authorized_policy() -> dict[str, object]:
    policy = load_external_policy(POLICY_PATH)
    policy["allowed_sources"] = [{"source_name": "authorized-test-feed", "source_version": "v1"}]
    return policy


def _events(*match_ids: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": list(match_ids),
            "event_id": [f"event-{index}" for index in range(len(match_ids))],
            "kickoff_utc": ["2025-01-01T15:00:00Z"] * len(match_ids),
        }
    )


def test_source_without_license_is_rejected() -> None:
    with pytest.raises(ValidationError, match="license"):
        _source(license_name=None, license_policy_reference=None)


def test_source_without_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _source(retrieved_at_utc=datetime(2025, 1, 1, 10, 0, tzinfo=None))


def test_snapshot_after_kickoff_is_rejected() -> None:
    with pytest.raises(ValidationError, match="precede kickoff"):
        _record(captured_at_utc="2025-01-01T15:00:00Z")


def test_snapshot_hash_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="64"):
        _record(input_sha256="not-a-sha")


def test_duplicate_snapshot_isolated() -> None:
    record = _record()
    report = audit_snapshot_records(
        [record.model_dump(mode="json"), record.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("m-001"),
    )
    assert report["valid_rows"] == 1
    assert report["matched_rows"] == 1
    assert report["duplicate_snapshots"] == 1
    assert report["source_rejections_by_reason"] == {"duplicate_snapshot": 1}


def test_unknown_and_ambiguous_matches_are_not_linked_randomly() -> None:
    record = _record()
    unknown = audit_snapshot_records(
        [record.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("other"),
    )
    assert unknown["unmatched_rows"] == 1
    ambiguous = audit_snapshot_records(
        [record.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("m-001", "m-001"),
    )
    assert ambiguous["ambiguous_rows"] == 1
    assert ambiguous["matched_rows"] == 0


def test_policy_protects_2526_and_2627(tmp_path: Path) -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    changed = copy.deepcopy(policy)
    changed["protected_seasons"]["future_holdout"] = []
    path = tmp_path / "bad-policy.yaml"
    path.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="2627"):
        load_external_policy(path)
    assert "2526" in policy["protected_seasons"]["forbid_tuning_selection_calibration"]


def test_unavailable_adapter_never_calls_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network must not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    adapter = UnavailableExternalAdapter()
    with pytest.raises(RuntimeError, match="configured"):
        adapter.fetch_snapshot()


def test_deferred_readiness_is_deterministic_and_has_no_economic_metrics(tmp_path: Path) -> None:
    policy = load_external_policy(POLICY_PATH)
    first = deferred_readiness_report(policy, policy_path=POLICY_PATH)
    second = deferred_readiness_report(policy, policy_path=POLICY_PATH)
    assert first == second
    assert first["external_source_status"] == "deferred_missing_authorized_source"
    assert first["source_status"] == "source_deferred"
    assert first["raw_rows"] == first["valid_rows"] == first["matched_rows"] == 0
    assert first["benchmark_status"] == "deferred"
    assert first["commercial_release"] is False
    assert not {"edge", "ev", "roi", "odds", "stake"}.intersection(first)
    output = tmp_path / "readiness.json"
    write_readiness_report(first, output)
    serialized = output.read_text(encoding="utf-8").lower()
    assert "api_key" not in serialized
    assert "secret" not in serialized
    assert json.loads(serialized)["commercial_release"] is False


def test_test_only_fixture_does_not_enter_metrics() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(policy, policy_path=POLICY_PATH)
    assert report["coverage"] == []
    assert report["license_failures"] == 0
    assert report["valid_rows"] == 0


def test_source_hash_mismatch_is_isolated() -> None:
    mismatched = _record(input_sha256="b" * 64)
    report = audit_snapshot_records(
        [mismatched.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("m-001"),
    )
    assert report["valid_rows"] == 0
    assert report["matched_rows"] == 0
    assert report["source_rejections_by_reason"] == {"input_hash_mismatch": 1}


def test_kickoff_matching_requires_declared_tolerance() -> None:
    record = _record(kickoff_utc="2025-01-01T15:06:00Z")
    report = audit_snapshot_records(
        [record.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("m-001"),
    )
    assert report["matched_rows"] == 0
    assert report["unmatched_rows"] == 1
    assert report["source_rejections_by_reason"] == {"kickoff_mismatch_outside_tolerance": 1}


def test_available_at_after_cutoff_is_late() -> None:
    record = _record(
        available_at_utc="2025-01-01T12:01:00Z",
        captured_at_utc="2025-01-01T13:00:00Z",
    )
    report = audit_snapshot_records(
        [record.model_dump(mode="json")],
        source=_source(),
        policy=_authorized_policy(),
        known_events=_events("m-001"),
        cutoff_utc=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert report["matched_rows"] == 0
    assert report["late_rows"] == 1
    assert report["source_rejections_by_reason"] == {"available_at_at_or_after_cutoff": 1}
