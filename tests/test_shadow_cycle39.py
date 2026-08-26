from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from football_prediction_lab.ingestion.local_csv import ingest_file
from football_prediction_lab.shadow.contracts import ShadowPrediction, ShadowRun
from football_prediction_lab.shadow.ledger import ShadowLedger
from football_prediction_lab.shadow.runner import run_shadow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
POLICY = ROOT / "configs" / "cycle36_future_holdout_policy.json"
AS_OF = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
TRAINING_CUTOFF = datetime(2024, 12, 31, 23, 59, tzinfo=UTC)


def _manifest(
    tmp_path: Path, input_path: Path = FIXTURE, *, max_rejection_rate: float = 0.25
) -> Path:
    result = ingest_file(
        input_path,
        run_id="ingest-shadow",
        output_root=tmp_path / "ingestion",
        source_name="cycle39-shadow-fixture",
        source_version="fixture-v1",
        license_or_usage_policy="test-only-fixture",
        season="2425",
        competition="EPL",
        max_rejection_rate=max_rejection_rate,
    )
    return result.manifest_path


def test_shadow_prediction_rejects_naive_or_late_timestamps() -> None:
    values = {
        "prediction_id": "p",
        "match_id": "m",
        "market": "btts",
        "market_definition": "both teams to score (BTTS)",
        "kickoff_utc": "2025-01-02T15:00:00+00:00",
        "issued_at_utc": "2025-01-01T12:00:00+00:00",
        "as_of_utc": "2025-01-01T12:00:00+00:00",
        "training_cutoff": "2024-12-31T23:59:00+00:00",
        "model_version": "model",
        "feature_version": "features",
        "policy_version": "policy",
        "probability": 0.5,
        "feature_provenance_hash": "feature-hash",
        "source_manifest_fingerprint": "manifest-hash",
        "selected_policy_variant": "constant_train_rate",
    }
    valid = ShadowPrediction.model_validate(values)
    assert valid.status == "issued"
    with pytest.raises(ValidationError, match="precede kickoff"):
        ShadowPrediction.model_validate({**values, "as_of_utc": "2025-01-02T15:00:00+00:00"})
    with pytest.raises(ValidationError, match="timezone"):
        ShadowPrediction.model_validate({**values, "kickoff_utc": "2025-01-02T15:00:00"})


def test_shadow_run_rejects_naive_and_commercial_release() -> None:
    values = {
        "run_id": "run",
        "as_of_utc": "2025-01-01T12:00:00+00:00",
        "started_at_utc": "2025-01-01T12:00:00+00:00",
        "completed_at_utc": "2025-01-01T12:00:01+00:00",
        "source_manifest_fingerprint": "manifest",
        "input_sha256": "input",
        "feature_input_sha256": "feature",
        "code_commit": "commit",
        "policy_version": "policy",
        "model_version": "model",
        "feature_version": "feature",
        "training_cutoff": "2024-12-31T23:59:00+00:00",
        "rows_seen": 1,
        "predictions_issued": 1,
        "rows_skipped": 0,
        "rejection_counts": {},
        "status": "completed",
        "output_sha256": "output",
        "ledger_sha256": "ledger",
    }
    assert ShadowRun.model_validate(values).commercial_release is False
    with pytest.raises(ValidationError, match="commercial_release"):
        ShadowRun.model_validate({**values, "commercial_release": True})


def test_shadow_issues_no_target_artifact_and_respects_as_of(tmp_path: Path) -> None:
    result = run_shadow(
        manifest_path=_manifest(tmp_path),
        as_of_utc=AS_OF,
        run_id="shadow-001",
        output_root=tmp_path / "shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    assert result["run"]["rows_seen"] == 3
    assert result["run"]["predictions_issued"] == 6
    assert result["run"]["rows_skipped"] == 0
    for prediction in result["artifact"]["predictions"]:
        assert not {"target", "result", "btts", "total_yellows_over_3_5"}.intersection(prediction)
        assert prediction["issued_at_utc"] <= prediction["as_of_utc"] < prediction["kickoff_utc"]
        assert prediction["training_cutoff"] < prediction["as_of_utc"]
    assert result["artifact"]["commercial_release"] is False
    assert {"target", "result"}.isdisjoint(result["artifact"]["skipped"])


def test_shadow_is_idempotent_across_runs_and_roots(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    first = run_shadow(
        manifest_path=manifest,
        as_of_utc=AS_OF,
        run_id="same-run",
        output_root=tmp_path / "root-a",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    second = run_shadow(
        manifest_path=manifest,
        as_of_utc=AS_OF,
        run_id="same-run",
        output_root=tmp_path / "root-b",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    assert (
        Path(first["predictions_path"]).read_bytes()
        == Path(second["predictions_path"]).read_bytes()
    )
    first_ids = [item["prediction_id"] for item in first["artifact"]["predictions"]]
    second_ids = [item["prediction_id"] for item in second["artifact"]["predictions"]]
    assert first_ids == second_ids
    assert first["run"]["output_sha256"] == second["run"]["output_sha256"]
    assert first["run"]["ledger_sha256"] == second["run"]["ledger_sha256"]
    assert len(ShadowLedger(Path(first["ledger_path"]).resolve()).records()) == 6


def test_shadow_ledger_rejects_mutation_and_does_not_duplicate(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    result = run_shadow(
        manifest_path=manifest,
        as_of_utc=AS_OF,
        run_id="ledger-run",
        output_root=tmp_path / "shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    ledger = ShadowLedger(Path(result["ledger_path"]))
    original_lines = Path(result["ledger_path"]).read_text(encoding="utf-8").splitlines()
    prediction = ShadowPrediction.model_validate(result["artifact"]["predictions"][0])
    ledger.append_prediction(prediction)
    assert Path(result["ledger_path"]).read_text(encoding="utf-8").splitlines() == original_lines
    tampered = json.loads(original_lines[0])
    tampered["record"]["probability"] = 0.99
    Path(result["ledger_path"]).write_text(
        json.dumps(tampered, sort_keys=True) + "\n" + "\n".join(original_lines[1:]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash"):
        ledger.verify()


def test_shadow_skips_late_and_reserved_rows(tmp_path: Path) -> None:
    frame = pd.read_csv(FIXTURE)
    frame["season"] = frame["season"].astype(str)
    frame.loc[0, "available_at_utc"] = "2025-01-02T10:00:00+00:00"
    frame.loc[1, "season"] = "2627"
    input_path = tmp_path / "late_and_reserved.csv"
    frame.to_csv(input_path, index=False)
    result = run_shadow(
        manifest_path=_manifest(tmp_path, input_path, max_rejection_rate=1.0),
        as_of_utc=AS_OF,
        run_id="skipped-run",
        output_root=tmp_path / "shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    assert result["run"]["predictions_issued"] == 2
    assert result["run"]["rows_skipped"] == 2
    assert result["run"]["rejection_counts"] == {
        "features_not_available_at_as_of": 1,
        "future_holdout_reserved": 1,
    }


def test_shadow_policy_rejects_2526_in_development(tmp_path: Path) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["development_seasons"].append("2526")
    bad_policy = tmp_path / "bad-policy.json"
    bad_policy.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="2526"):
        run_shadow(
            manifest_path=_manifest(tmp_path),
            as_of_utc=AS_OF,
            run_id="bad-policy",
            output_root=tmp_path / "shadow",
            policy_path=bad_policy,
            training_cutoff=TRAINING_CUTOFF,
        )


def test_shadow_missing_probability_has_explicit_skip_reason(tmp_path: Path) -> None:
    frame = pd.read_csv(FIXTURE).drop(columns=["probability_cards"])
    input_path = tmp_path / "missing-cards.csv"
    frame.to_csv(input_path, index=False)
    result = run_shadow(
        manifest_path=_manifest(tmp_path, input_path),
        as_of_utc=AS_OF,
        run_id="missing-cards-run",
        output_root=tmp_path / "shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    assert result["run"]["predictions_issued"] == 3
    assert result["run"]["rows_skipped"] == 3
    assert result["run"]["rejection_counts"] == {"missing_frozen_probability_cards": 3}
    assert all(
        item["reason"] == "missing_frozen_probability" for item in result["artifact"]["skipped"]
    )


def test_changed_frozen_probability_changes_prediction_identity(tmp_path: Path) -> None:
    first = _manifest(tmp_path / "first")
    changed_frame = pd.read_csv(FIXTURE)
    changed_frame.loc[0, "probability_btts"] = 0.63
    changed_input = tmp_path / "changed" / "input.csv"
    changed_input.parent.mkdir(parents=True)
    changed_frame.to_csv(changed_input, index=False)
    changed = _manifest(tmp_path / "changed", changed_input)
    first_result = run_shadow(
        manifest_path=first,
        as_of_utc=AS_OF,
        run_id="first-run",
        output_root=tmp_path / "first-shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    changed_result = run_shadow(
        manifest_path=changed,
        as_of_utc=AS_OF,
        run_id="changed-run",
        output_root=tmp_path / "changed-shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    first_ids = {item["prediction_id"] for item in first_result["artifact"]["predictions"]}
    changed_ids = {item["prediction_id"] for item in changed_result["artifact"]["predictions"]}
    assert first_ids != changed_ids


def test_existing_prediction_artifact_is_not_mutated(tmp_path: Path) -> None:
    result = run_shadow(
        manifest_path=_manifest(tmp_path),
        as_of_utc=AS_OF,
        run_id="immutable-run",
        output_root=tmp_path / "shadow",
        policy_path=POLICY,
        training_cutoff=TRAINING_CUTOFF,
    )
    predictions_path = Path(result["predictions_path"])
    original = predictions_path.read_bytes()
    predictions_path.write_bytes(
        original.replace(b'"commercial_release": false', b'"commercial_release": true')
    )
    with pytest.raises(ValueError, match="prediction artifact conflict"):
        run_shadow(
            manifest_path=_manifest(tmp_path / "rerun"),
            as_of_utc=AS_OF,
            run_id="immutable-run",
            output_root=tmp_path / "shadow",
            policy_path=POLICY,
            training_cutoff=TRAINING_CUTOFF,
        )
    assert predictions_path.read_bytes() != original
    assert b'"commercial_release": true' in predictions_path.read_bytes()
