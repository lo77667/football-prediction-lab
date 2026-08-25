import hashlib
import json
from pathlib import Path

from football_prediction_lab.evaluation.source_readiness import (
    select_manifested_source_files,
)


def manifest_for(source: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "feature_version": "test",
        "first_datetime": "2024-01-01T00:00:00Z",
        "last_datetime": "2025-01-01T00:00:00Z",
        "license_policy": "internal_licensed",
    }
    values.update(overrides)
    return values


def write_manifest(source: Path, manifest: dict[str, object]) -> None:
    Path(f"{source}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_source_readiness_is_no_go_without_manifest(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "missing_manifest"


def test_source_readiness_requires_verified_license(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    write_manifest(source, manifest_for(source, license_policy="unknown"))
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "unverified_license_policy"


def test_source_readiness_rejects_input_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    write_manifest(source, manifest_for(source, input_sha256="a" * 64))
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "input_sha256_mismatch"


def test_source_readiness_excludes_protected_season(tmp_path: Path) -> None:
    source = tmp_path / "2526_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "no_go"
    assert result["rejected_files"][0]["reason"] == "protected_season"


def test_source_readiness_selects_complete_manifest(tmp_path: Path) -> None:
    source = tmp_path / "2425_E0.csv"
    source.write_text("header\n", encoding="utf-8")
    write_manifest(source, manifest_for(source))
    result = select_manifested_source_files([source])
    assert result["selection_status"] == "eligible"
    assert result["selected_files"] == [str(source)]
