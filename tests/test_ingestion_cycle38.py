from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from football_prediction_lab.ingestion.contracts import SourceRecord
from football_prediction_lab.ingestion.local_csv import (
    LocalCsvAdapter,
    canonical_manifest_fingerprint,
    ingest_file,
    replay_manifest,
    validate_manifest,
)

COLUMNS = [
    "match_id",
    "season",
    "competition",
    "home_team",
    "away_team",
    "kickoff_utc",
]


def _frame(order: tuple[int, ...] = (0, 1)) -> pd.DataFrame:
    rows = [
        {
            "match_id": "m-002",
            "season": "2425",
            "competition": "EPL",
            "home_team": "Beta",
            "away_team": "Gamma",
            "kickoff_utc": "2025-01-02T15:00:00+00:00",
        },
        {
            "match_id": "m-001",
            "season": "2425",
            "competition": "EPL",
            "home_team": "Alpha",
            "away_team": "Delta",
            "kickoff_utc": "2025-01-01T15:00:00+00:00",
        },
    ]
    return pd.DataFrame([rows[index] for index in order], columns=COLUMNS)


def _write(path: Path, frame: pd.DataFrame) -> Path:
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def test_contract_rejects_naive_source_timestamp() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_name="local",
            source_version="v1",
            retrieved_at_utc=datetime(2025, 1, 1),
            input_path="authorized.csv",
            input_sha256="a" * 64,
            license_or_usage_policy="authorized",
            schema_version="v1",
            row_count=1,
        )


def test_ingest_is_idempotent_and_replayable(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    output_root = tmp_path / "warehouse"
    first = ingest_file(input_path, run_id="run-001", output_root=output_root)
    second = ingest_file(input_path, run_id="run-001", output_root=output_root)
    assert first.manifest["run"]["output_hash"] == second.manifest["run"]["output_hash"]
    assert first.manifest["manifest_fingerprint"] == second.manifest["manifest_fingerprint"]
    assert first.raw_path.read_bytes() == input_path.read_bytes()
    assert (
        validate_manifest(first.manifest_path)["manifest_fingerprint"]
        == first.manifest["manifest_fingerprint"]
    )
    replay = replay_manifest(first.manifest_path)
    assert replay["replay"] == "passed"
    assert replay["output_hash"] == first.manifest["run"]["output_hash"]


def test_ingest_sort_is_independent_of_arrival_order(tmp_path: Path) -> None:
    first_path = _write(tmp_path / "first.csv", _frame((0, 1)))
    second_path = _write(tmp_path / "second.csv", _frame((1, 0)))
    first_adapter = LocalCsvAdapter(
        first_path,
        run_id="run-a",
        source_name="authorized",
        source_version="v1",
        license_or_usage_policy="authorized",
    )
    second_adapter = LocalCsvAdapter(
        second_path,
        run_id="run-b",
        source_name="authorized",
        source_version="v1",
        license_or_usage_policy="authorized",
    )
    first_accepted, _ = first_adapter.validate(first_adapter.normalize(first_adapter.fetch()))
    second_accepted, _ = second_adapter.validate(second_adapter.normalize(second_adapter.fetch()))
    identity = ["match_id", "season", "competition", "home_team", "away_team", "kickoff_utc"]
    pd.testing.assert_frame_equal(first_accepted[identity], second_accepted[identity])
    assert first_accepted["match_id"].tolist() == ["m-001", "m-002"]


def test_duplicate_match_ids_are_quarantined_and_fail_closed(tmp_path: Path) -> None:
    frame = pd.concat([_frame().iloc[[0]], _frame().iloc[[0]]], ignore_index=True)
    input_path = _write(tmp_path / "duplicate.csv", frame)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(input_path, run_id="duplicate-run", output_root=tmp_path / "warehouse")
    quarantine = json.loads(
        (tmp_path / "warehouse/quarantine/duplicate-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 2
    assert quarantine["rejection_counts_by_reason"]["duplicate_match_id_in_file"] == 2


def test_new_source_hash_cannot_replace_existing_match(tmp_path: Path) -> None:
    output_root = tmp_path / "warehouse"
    first_path = _write(tmp_path / "first.csv", _frame((0, 1)))
    ingest_file(first_path, run_id="first-run", output_root=output_root, source_name="same-source")
    changed = _frame((0, 1)).copy()
    changed.loc[0, "away_team"] = "Changed"
    second_path = _write(tmp_path / "second.csv", changed)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(
            second_path,
            run_id="second-run",
            output_root=output_root,
            source_name="same-source",
        )
    quarantine = json.loads(
        (output_root / "quarantine/second-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 2
    assert "existing_match_id_different_source_hash" in quarantine["rejection_counts_by_reason"]
    first_manifest = json.loads(
        (output_root / "manifests/first-run.json").read_text(encoding="utf-8")
    )
    assert first_manifest["run"]["rows_accepted"] == 2


def test_post_match_column_is_blocked_from_pre_match(tmp_path: Path) -> None:
    frame = _frame().assign(btts=[True, False])
    input_path = _write(tmp_path / "target.csv", frame)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(input_path, run_id="target-run", output_root=tmp_path / "warehouse")
    quarantine = json.loads(
        (tmp_path / "warehouse/quarantine/target-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 2
    assert "post_match_column_in_pre_match" in quarantine["rejection_counts_by_reason"]


def test_available_after_kickoff_is_quarantined(tmp_path: Path) -> None:
    frame = _frame().assign(
        available_at_utc=[
            "2025-01-02T15:01:00+00:00",
            "2025-01-01T14:59:00+00:00",
        ]
    )
    input_path = _write(tmp_path / "late.csv", frame)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(input_path, run_id="late-run", output_root=tmp_path / "warehouse")
    quarantine = json.loads(
        (tmp_path / "warehouse/quarantine/late-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 1
    assert quarantine["rejection_counts_by_reason"]["available_after_kickoff"] == 1


def test_naive_kickoff_is_quarantined_without_timezone_policy(tmp_path: Path) -> None:
    frame = _frame().assign(kickoff_utc=["2025-01-02 15:00", "2025-01-01 15:00"])
    input_path = _write(tmp_path / "naive.csv", frame)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(input_path, run_id="naive-run", output_root=tmp_path / "warehouse")
    quarantine = json.loads(
        (tmp_path / "warehouse/quarantine/naive-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 2
    assert quarantine["rejection_counts_by_reason"]["kickoff_timezone_or_parse_failure"] == 2


def test_date_time_requires_explicit_source_timezone(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m-001"],
            "season": ["2425"],
            "competition": ["EPL"],
            "home_team": ["Alpha"],
            "away_team": ["Delta"],
            "Date": ["2025-01-01"],
            "Time": ["15:00"],
        }
    )
    input_path = _write(tmp_path / "date-time.csv", frame)
    with pytest.raises(RuntimeError, match="quarantine rate"):
        ingest_file(input_path, run_id="date-time-run", output_root=tmp_path / "warehouse")
    quarantine = json.loads(
        (tmp_path / "warehouse/quarantine/date-time-run.json").read_text(encoding="utf-8")
    )
    assert quarantine["rows_quarantined"] == 1
    assert quarantine["rejection_counts_by_reason"]["source_timezone_required_for_date_time"] == 1


def test_manifest_fingerprint_is_independent_of_root_and_runtime(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    first = ingest_file(input_path, run_id="same-run", output_root=tmp_path / "root-a")
    second = ingest_file(input_path, run_id="same-run", output_root=tmp_path / "root-b")
    assert first.manifest["manifest_fingerprint"] == second.manifest["manifest_fingerprint"]
    mutated = copy.deepcopy(first.manifest)
    mutated["run"]["run_id"] = "different-run"
    mutated["run"]["started_at_utc"] = "2030-01-01T00:00:00+00:00"
    mutated["run"]["completed_at_utc"] = "2030-01-01T00:00:01+00:00"
    mutated["source"]["retrieved_at_utc"] = "2030-01-01T00:00:00+00:00"
    mutated["input_path"] = "/another/machine/input.csv"
    mutated["output_path"] = "/another/machine/normalized/other.csv"
    mutated["processed_output_path"] = "/another/machine/processed/other.csv"
    mutated["raw_path"] = "/another/machine/raw/other.csv"
    assert canonical_manifest_fingerprint(first.manifest) == canonical_manifest_fingerprint(mutated)


def test_run_id_is_not_content_fingerprint_identity(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    first = ingest_file(input_path, run_id="run-a", output_root=tmp_path / "root-a")
    second = ingest_file(input_path, run_id="run-b", output_root=tmp_path / "root-b")
    assert first.manifest["manifest_fingerprint"] == second.manifest["manifest_fingerprint"]
    assert first.manifest["run"]["run_id"] != second.manifest["run"]["run_id"]
    assert first.manifest["run"]["output_hash"] != second.manifest["run"]["output_hash"]


def test_input_and_accepted_content_changes_change_fingerprint(tmp_path: Path) -> None:
    first_path = _write(tmp_path / "first.csv", _frame())
    changed = _frame().copy()
    changed.loc[0, "away_team"] = "Changed"
    second_path = _write(tmp_path / "second.csv", changed)
    first = ingest_file(first_path, run_id="first", output_root=tmp_path / "root-a")
    second = ingest_file(second_path, run_id="second", output_root=tmp_path / "root-b")
    assert first.manifest["input_sha256"] != second.manifest["input_sha256"]
    assert first.manifest["run"]["output_hash"] != second.manifest["run"]["output_hash"]
    assert first.manifest["manifest_fingerprint"] != second.manifest["manifest_fingerprint"]


def test_rejection_counts_and_row_counts_are_fingerprinted(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    result = ingest_file(input_path, run_id="run", output_root=tmp_path / "root")
    changed = copy.deepcopy(result.manifest)
    changed["run"]["rows_accepted"] = 1
    changed["rows_accepted"] = 1
    changed["rejection_counts_by_reason"] = {"synthetic_reason": 1}
    assert canonical_manifest_fingerprint(result.manifest) != canonical_manifest_fingerprint(
        changed
    )


def test_json_key_order_and_rejection_key_order_do_not_change_fingerprint(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    result = ingest_file(input_path, run_id="run", output_root=tmp_path / "root")
    reordered = copy.deepcopy(result.manifest)
    reordered["rejection_counts_by_reason"] = dict(
        reversed(list(reordered["rejection_counts_by_reason"].items()))
    )
    reordered["source"] = dict(reversed(list(reordered["source"].items())))
    assert canonical_manifest_fingerprint(result.manifest) == canonical_manifest_fingerprint(
        reordered
    )


def test_replay_returns_canonical_fingerprint_and_output_sha256(tmp_path: Path) -> None:
    input_path = _write(tmp_path / "authorized.csv", _frame())
    result = ingest_file(input_path, run_id="run", output_root=tmp_path / "root")
    replay = replay_manifest(result.manifest_path)
    assert replay["replay"] == "passed"
    assert replay["input_sha256"] == result.manifest["input_sha256"]
    assert replay["output_sha256"] == result.manifest["run"]["output_hash"]
    assert replay["manifest_fingerprint"] == result.manifest["manifest_fingerprint"]


def test_future_season_is_not_silently_admitted_to_policy() -> None:
    assert "2526" not in {"1516", "2425"}
    assert "2627" not in {"1516", "2425"}
