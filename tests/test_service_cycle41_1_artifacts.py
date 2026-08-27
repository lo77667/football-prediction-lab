from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.artifact_validation import validate_service_run

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "cycle36_future_holdout_policy.json"
SMOKE_SCRIPT = ROOT / "scripts" / "ops" / "scripts_run_service_smoke.py"
VALIDATOR_SCRIPT = ROOT / "scripts" / "ops" / "scripts_validate_service_response.py"


def _run_smoke(root: Path) -> tuple[Path, dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--output-root", str(root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    run_dir = Path(values["run_dir"])
    return run_dir, values


def _manifest(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "service_manifest.json").read_text(encoding="utf-8"))


def test_atomic_service_run_validates_all_artifacts(tmp_path: Path) -> None:
    run_dir, values = _run_smoke(tmp_path / "runs")
    result = validate_service_run(run_dir)
    assert result["validation"] == "passed"
    assert result["run_fingerprint"] == values["run_fingerprint"]
    assert result["predictions_count"] == 6
    assert result["response_predictions_count"] == 3
    assert result["ledger_records_count"] == 6
    assert result["commercial_release"] is False
    assert {path.name for path in run_dir.iterdir()} == {
        "service_request.json",
        "service_response.json",
        "service_manifest.json",
        "shadow_ledger.jsonl",
        "predictions_prelabel.jsonl",
        "validation.json",
    }


def test_health_requires_complete_atomic_run(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    application = PredictionApplication(
        policy_path=POLICY_PATH,
        allowed_manifest_root=tmp_path / "runs",
        output_root=tmp_path / "service-output",
        code_root=ROOT,
    )
    assert application.health(run_dir)["status"] == "healthy"
    (run_dir / "shadow_ledger.jsonl").unlink()
    assert application.health(run_dir)["status"] == "blocked_provenance"


def test_missing_ledger_fails_closed(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    (run_dir / "shadow_ledger.jsonl").unlink()
    with pytest.raises(FileNotFoundError, match="ledger"):
        validate_service_run(run_dir)
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_SCRIPT),
            "--response",
            str(run_dir / "service_response.json"),
            "--ledger",
            str(tmp_path / "missing-ledger.jsonl"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_empty_ledger_fails_when_response_declares_six(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    (run_dir / "shadow_ledger.jsonl").write_text("", encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_service_run(run_dir)


def test_ledger_record_count_mismatch_fails(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    response_path = run_dir / "service_response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["operational_metrics"]["ledger_records"] = 5
    response_path.write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="response_content_sha256|record count|ledger_records"):
        validate_service_run(run_dir)


def test_ledger_sha_mismatch_fails(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    manifest_path = run_dir / "service_manifest.json"
    manifest = _manifest(run_dir)
    manifest["ledger_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="service manifest mismatch: ledger_sha256"):
        validate_service_run(run_dir)


def test_mixed_commit_or_request_fingerprint_fails(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    manifest_path = run_dir / "service_manifest.json"
    manifest = _manifest(run_dir)
    manifest["code_commit"] = "0" * 40
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="service manifest mismatch: code_commit"):
        validate_service_run(run_dir)
    manifest["code_commit"] = json.loads(
        (run_dir / "service_response.json").read_text(encoding="utf-8")
    )["code_commit"]
    manifest["request_fingerprint"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="service manifest mismatch: request_fingerprint"):
        validate_service_run(run_dir)


def test_prediction_artifact_and_ledger_ids_are_consistent(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    predictions = [
        json.loads(line)
        for line in (run_dir / "predictions_prelabel.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    response = json.loads((run_dir / "service_response.json").read_text(encoding="utf-8"))
    ledger = [
        json.loads(line)
        for line in (run_dir / "shadow_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(predictions) == len(ledger) == 6
    assert len(response["predictions"]) == 3
    assert [item["prediction"]["prediction_id"] for item in predictions] == [
        item["record_id"] for item in ledger
    ]
    assert response["operational_metrics"]["ledger_markets"] == ["btts", "cards"]


def test_output_roots_have_same_semantic_fingerprint_and_response_hash(tmp_path: Path) -> None:
    run_a, values_a = _run_smoke(tmp_path / "root-a")
    run_b, values_b = _run_smoke(tmp_path / "root-b")
    response_a = json.loads((run_a / "service_response.json").read_text(encoding="utf-8"))
    response_b = json.loads((run_b / "service_response.json").read_text(encoding="utf-8"))
    assert values_a["run_fingerprint"] == values_b["run_fingerprint"]
    assert response_a["request_fingerprint"] == response_b["request_fingerprint"]
    assert response_a["response_content_sha256"] == response_b["response_content_sha256"]


def test_response_without_ledger_argument_fails_when_ledger_count_is_positive(
    tmp_path: Path,
) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_SCRIPT),
            "--response",
            str(run_dir / "service_response.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "ledger" in result.stderr.lower()


def test_stale_manifest_and_response_financial_fields_fail(tmp_path: Path) -> None:
    run_dir, _ = _run_smoke(tmp_path / "runs")
    manifest_path = run_dir / "service_manifest.json"
    manifest = _manifest(run_dir)
    manifest["response_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="service manifest mismatch: response_sha256"):
        validate_service_run(run_dir)
    response_path = run_dir / "service_response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["odds"] = {"home": 2.0}
    response_path.write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="forbidden"):
        validate_service_run(run_dir)
