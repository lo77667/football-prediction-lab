from __future__ import annotations

import copy
import json
import socket
import subprocess
import sys
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
    build_deferred_manifest,
    canonical_report_payload,
    deferred_readiness_report,
    load_external_policy,
    report_content_sha256,
    validate_deferred_manifest,
    validate_readiness_report,
    write_manifest,
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


def test_output_roots_and_runtime_metadata_do_not_change_canonical_hash(tmp_path: Path) -> None:
    policy = load_external_policy(POLICY_PATH)
    first = deferred_readiness_report(
        policy,
        policy_path=tmp_path / "checkout-a" / "configs" / POLICY_PATH.name,
        source_commit="same-commit",
        runtime_metadata={
            "report_path": "/checkout-a/reports/readiness.json",
            "output_root": "/checkout-a/reports",
            "hostname": "host-a",
            "generated_at_utc": "2026-08-26T13:00:00Z",
        },
    )
    second = deferred_readiness_report(
        policy,
        policy_path=tmp_path / "checkout-b" / "configs" / POLICY_PATH.name,
        source_commit="same-commit",
        runtime_metadata={
            "report_path": "/checkout-b/reports/readiness.json",
            "output_root": "/checkout-b/reports",
            "hostname": "host-b",
            "generated_at_utc": "2030-01-01T00:00:00Z",
        },
    )
    assert first["report_content_sha256"] == second["report_content_sha256"]
    assert report_content_sha256(first) == report_content_sha256(second)
    assert first["runtime_metadata"] != second["runtime_metadata"]


def test_canonical_payload_has_no_absolute_paths_or_runtime_fields() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(
        policy,
        policy_path=Path("/different/checkout/configs/cycle40_external_source_policy.yaml"),
        source_commit="commit-1",
        runtime_metadata={
            "report_path": "/different/output/report.json",
            "output_root": "/different/output",
            "hostname": "runner-1",
            "generated_at_utc": "2026-08-26T13:00:00Z",
        },
    )
    canonical = canonical_report_payload(report)
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    assert "/checkout" not in serialized
    assert "/different" not in serialized
    assert "runtime_metadata" not in canonical
    assert "policy_path" not in canonical
    assert "report_path" not in canonical
    assert "hostname" not in serialized
    assert "generated_at_utc" not in serialized


def test_reordering_json_keys_does_not_change_canonical_hash() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(policy, source_commit="commit-1")
    reordered = {key: report[key] for key in reversed(list(report))}
    assert report_content_sha256(report) == report_content_sha256(reordered)


def test_policy_content_change_changes_policy_and_report_hash() -> None:
    policy = load_external_policy(POLICY_PATH)
    changed = copy.deepcopy(policy)
    changed["cutoff_protocol"]["max_age_hours"] = 48
    first = deferred_readiness_report(policy, source_commit="commit-1")
    second = deferred_readiness_report(changed, source_commit="commit-1")
    assert first["policy_sha256"] != second["policy_sha256"]
    assert first["report_content_sha256"] != second["report_content_sha256"]


def test_readiness_counter_or_status_change_changes_report_hash() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(policy, source_commit="commit-1")
    changed_counter = dict(report)
    changed_counter["raw_rows"] = 1
    changed_status = dict(report)
    changed_status["source_status"] = "source_rejected"
    assert report_content_sha256(report) != report_content_sha256(changed_counter)
    assert report_content_sha256(report) != report_content_sha256(changed_status)


def test_validator_recomputes_content_hash_without_path_comparison() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(
        policy,
        policy_path=Path("/checkout-a/configs/cycle40_external_source_policy.yaml"),
        source_commit="commit-1",
        runtime_metadata={"report_path": "/checkout-a/out/report.json"},
    )
    result = validate_readiness_report(report, policy)
    assert result["report_content_sha256"] == report["report_content_sha256"]
    assert result["absolute_paths_in_canonical"] is False
    assert result["commercial_release"] is False


def test_write_report_distinguishes_file_hash_from_content_hash(tmp_path: Path) -> None:
    policy = load_external_policy(POLICY_PATH)
    first = deferred_readiness_report(policy, source_commit="commit-1")
    second = deferred_readiness_report(policy, source_commit="commit-1")
    file_a = tmp_path / "a" / "report.json"
    file_b = tmp_path / "b" / "report.json"
    file_hash_a = write_readiness_report(
        first, file_a, runtime_metadata={"report_path": str(file_a)}
    )
    file_hash_b = write_readiness_report(
        second, file_b, runtime_metadata={"report_path": str(file_b)}
    )
    assert first["report_content_sha256"] == second["report_content_sha256"]
    assert file_hash_a != file_hash_b
    assert file_hash_a != first["report_content_sha256"]


def test_zero_sources_cannot_become_verified() -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(policy)
    assert report["source_count"] == 0
    assert report["external_source_status"] == "deferred_missing_authorized_source"
    assert report["source_status"] == "source_deferred"
    with pytest.raises(ValueError, match="zero sources"):
        invalid = dict(report)
        invalid["source_status"] = "source_verified"
        invalid["report_content_sha256"] = report_content_sha256(invalid)
        validate_readiness_report(invalid, policy)


def test_deferred_manifest_links_content_hash_but_not_file_location(tmp_path: Path) -> None:
    policy = load_external_policy(POLICY_PATH)
    report = deferred_readiness_report(policy, source_commit="commit-1")
    manifest = build_deferred_manifest(report)
    path_a = tmp_path / "checkout-a" / "manifest.json"
    path_b = tmp_path / "checkout-b" / "manifest.json"
    file_hash_a = write_manifest(manifest, path_a)
    file_hash_b = write_manifest(manifest, path_b)
    assert file_hash_a == file_hash_b
    assert manifest["report_content_sha256"] == report["report_content_sha256"]
    assert validate_deferred_manifest(manifest, report, policy)["manifest_content_valid"] is True


def test_cli_is_portable_across_two_checkout_and_output_roots(tmp_path: Path) -> None:
    checkout_a = tmp_path / "checkout-a"
    checkout_b = tmp_path / "checkout-b"
    output_a = checkout_a / "reports" / "readiness.json"
    output_b = checkout_b / "reports" / "readiness.json"
    policy_a = checkout_a / "configs" / POLICY_PATH.name
    policy_b = checkout_b / "configs" / POLICY_PATH.name
    policy_a.parent.mkdir(parents=True)
    policy_b.parent.mkdir(parents=True)
    policy_a.write_bytes(POLICY_PATH.read_bytes())
    policy_b.write_bytes(POLICY_PATH.read_bytes())
    command = [
        sys.executable,
        str(ROOT / "scripts_audit_external_source.py"),
        "--mode",
        "readiness",
        "--policy",
        str(policy_a),
        "--output",
        str(output_a),
        "--manifest-output",
        str(checkout_a / "reports" / "manifest.json"),
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    command[command.index(str(policy_a))] = str(policy_b)
    command[command.index(str(output_a))] = str(output_b)
    command[command.index(str(checkout_a / "reports" / "manifest.json"))] = str(
        checkout_b / "reports" / "manifest.json"
    )
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    report_a = json.loads(output_a.read_text(encoding="utf-8"))
    report_b = json.loads(output_b.read_text(encoding="utf-8"))
    assert report_a["report_content_sha256"] == report_b["report_content_sha256"]
    assert report_a["policy_sha256"] == report_b["policy_sha256"]
    assert report_a["runtime_metadata"] != report_b["runtime_metadata"]
    assert report_a["external_source_status"] == "deferred_missing_authorized_source"
    assert "source_verified" not in {report_a["source_status"], report_b["source_status"]}
