import json
from pathlib import Path

from football_prediction_lab.evaluation.source_readiness import (
    select_manifested_source_files,
)


def test_source_readiness_is_no_go_without_manifest(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "missing_manifest"


def test_source_readiness_requires_verified_license(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    manifest = {
        "input_sha256": "a" * 64,
        "feature_version": "test",
        "first_datetime": "2024-01-01T00:00:00Z",
        "last_datetime": "2025-01-01T00:00:00Z",
        "license_policy": "unknown",
    }
    Path(f"{source}.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "unverified_license_policy"


def test_source_readiness_excludes_protected_season(tmp_path: Path) -> None:
    source = tmp_path / "2526_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "protected_season"


def test_source_readiness_selects_complete_manifest(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    manifest = {
        "input_sha256": "a" * 64,
        "feature_version": "test",
        "first_datetime": "2024-01-01T00:00:00Z",
        "last_datetime": "2025-01-01T00:00:00Z",
        "license_policy": "internal_licensed",
    }
    Path(f"{source}.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "eligible"
    assert result["selected_files"] == [str(source)]
