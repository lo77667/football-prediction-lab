from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from football_prediction_lab.ingestion.local_csv import ingest_file
from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.contracts import PredictionServiceRequest
from football_prediction_lab.service.errors import PredictionServiceError
from football_prediction_lab.service.transport import post_shadow_prediction
from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    SERVICE_VERSION,
    code_commit,
)
from football_prediction_lab.shadow.ledger import ShadowLedger

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "cycle36_future_holdout_policy.json"
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
)


def _prepare(
    tmp_path: Path, input_path: Path = FIXTURE_PATH
) -> tuple[PredictionApplication, dict[str, object]]:
    ingestion_root = tmp_path / "ingestion"
    result = ingest_file(
        input_path,
        run_id="service-input",
        output_root=ingestion_root,
        source_name="cycle41-test-local",
        source_version="cycle41-test-v1",
        license_or_usage_policy="test-only; no redistribution",
        season="2425",
        competition="EPL",
        code_commit=code_commit(ROOT),
        max_rejection_rate=1.0,
    )
    application = PredictionApplication(
        policy_path=POLICY_PATH,
        allowed_manifest_root=ingestion_root,
        output_root=tmp_path / "service-output",
        code_root=ROOT,
    )
    return application, result.manifest


def _request(
    manifest: dict[str, object], request_id: str = "req-001", **overrides: object
) -> dict[str, object]:
    values: dict[str, object] = {
        "request_id": request_id,
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "as_of_utc": "2025-01-01T12:00:00Z",
        "market": "btts",
        "policy_version": POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "expected_source_commit": code_commit(ROOT),
        "mode": "shadow",
    }
    values.update(overrides)
    return values


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key).lower())
            found.update(_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_keys(child))
    return found


def test_health_is_not_ready_without_verified_manifest_and_has_safe_version() -> None:
    application = PredictionApplication(
        policy_path=POLICY_PATH,
        allowed_manifest_root=ROOT / "tests" / "fixtures",
        output_root=ROOT / "reports" / "generated" / "cycle_41_service_smoke",
        code_root=ROOT,
    )
    assert application.health()["status"] == "not_ready"
    version = application.version()
    assert version["service_version"] == SERVICE_VERSION
    assert version["commercial_release"] is False
    assert not any(str(value).startswith("/") for value in version.values())
    assert "secret" not in json.dumps(version).lower()


def test_valid_manifest_can_be_healthy_and_path_traversal_is_blocked(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    manifest_path = tmp_path / "ingestion" / "manifests" / "service-input.json"
    assert application.health(manifest_path)["status"] == "healthy"
    assert (
        application.health(tmp_path / "outside" / "escape.json")["status"] == "blocked_provenance"
    )
    assert manifest["manifest_fingerprint"]


def test_service_returns_prelabel_predictions_and_ledger_records(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    response = application.predict(PredictionServiceRequest.model_validate(_request(manifest)))
    assert response.service_version == SERVICE_VERSION
    assert len(response.predictions) == 3
    assert response.operational_metrics.predictions_issued == 3
    assert response.commercial_release is False
    assert not {"target", "result", "odds", "roi", "ev", "stake"}.intersection(
        _keys(response.model_dump(mode="json"))
    )
    ledger_path = tmp_path / "service-output" / "ledger" / "predictions.jsonl"
    ledger = ShadowLedger(ledger_path)
    ledger.verify()
    assert len(ledger.records()) == 6


def test_same_semantic_request_is_idempotent_and_request_id_is_metadata(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    first = application.predict(
        PredictionServiceRequest.model_validate(_request(manifest, "req-a"))
    )
    second = application.predict(
        PredictionServiceRequest.model_validate(_request(manifest, "req-b"))
    )
    assert first.response_content_sha256 == second.response_content_sha256
    assert [item.prediction_id for item in first.predictions] == [
        item.prediction_id for item in second.predictions
    ]
    assert [item.probability for item in first.predictions] == [
        item.probability for item in second.predictions
    ]
    assert second.operational_metrics.idempotent_replay is True
    ledger = ShadowLedger(tmp_path / "service-output" / "ledger" / "predictions.jsonl")
    ledger.verify()
    assert len(ledger.records()) == 6


def test_output_root_does_not_change_response_content_hash(tmp_path: Path) -> None:
    app_a, manifest = _prepare(tmp_path / "a")
    app_b, _ = _prepare(tmp_path / "b")
    request = PredictionServiceRequest.model_validate(_request(manifest))
    response_a = app_a.predict(request)
    response_b = app_b.predict(request)
    assert response_a.response_content_sha256 == response_b.response_content_sha256
    assert [item.prediction_id for item in response_a.predictions] == [
        item.prediction_id for item in response_b.predictions
    ]


def test_request_contract_rejects_sensitive_or_forbidden_fields(tmp_path: Path) -> None:
    _, manifest = _prepare(tmp_path)
    payload = _request(manifest)
    payload["odds"] = {"home": 2.0}
    result = post_shadow_prediction(_prepare(tmp_path / "again")[0], payload)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"
    payload = _request(manifest, request_id="/absolute/path")
    result = post_shadow_prediction(_prepare(tmp_path / "third")[0], payload)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_fingerprint", "0" * 64),
        ("policy_version", "wrong-policy"),
        ("model_version", "wrong-model"),
        ("feature_version", "wrong-feature"),
        ("expected_source_commit", "0" * 40),
    ],
)
def test_request_rejects_provenance_or_version_mismatch(
    tmp_path: Path, field: str, value: object
) -> None:
    application, manifest = _prepare(tmp_path)
    result = post_shadow_prediction(application, _request(manifest, **{field: value}))
    assert result["ok"] is False
    assert result["error"]["code"] in {"contract_mismatch", "blocked_provenance"}


def test_request_rejects_as_of_after_kickoff(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    result = post_shadow_prediction(
        application,
        _request(manifest, as_of_utc="2025-01-02T00:00:00Z"),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"
    assert result["error"]["field"] == "as_of_utc"


def test_2627_is_reserved_and_not_issued(tmp_path: Path) -> None:
    source = pd.read_csv(FIXTURE_PATH)
    source["season"] = "2627"
    input_path = tmp_path / "future-2627.csv"
    source.to_csv(input_path, index=False)
    application, manifest = _prepare(tmp_path / "reserved", input_path)
    response = application.predict(PredictionServiceRequest.model_validate(_request(manifest)))
    assert response.predictions == []
    assert any(item.get("reason") == "future_holdout_reserved" for item in response.skipped)
    assert response.commercial_release is False


def test_invalid_probability_is_rejected_before_runner(tmp_path: Path) -> None:
    source = pd.read_csv(FIXTURE_PATH)
    source.loc[0, "probability_btts"] = 1.5
    input_path = tmp_path / "invalid-probability.csv"
    source.to_csv(input_path, index=False)
    application, manifest = _prepare(tmp_path / "invalid", input_path)
    result = post_shadow_prediction(application, _request(manifest))
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"


def test_target_tampering_is_blocked_by_verified_manifest(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    processed_path = Path(str(manifest["processed_output_path"]))
    frame = pd.read_csv(processed_path)
    frame["target"] = 1
    frame.to_csv(processed_path, index=False)
    result = post_shadow_prediction(application, _request(manifest))
    assert result["ok"] is False
    assert result["error"]["code"] == "blocked_provenance"


def test_response_hash_is_canonical_and_changes_with_semantic_request(tmp_path: Path) -> None:
    application, manifest = _prepare(tmp_path)
    first = application.predict(PredictionServiceRequest.model_validate(_request(manifest)))
    changed = application.predict(
        PredictionServiceRequest.model_validate(
            _request(manifest, as_of_utc="2025-01-01T13:00:00Z")
        )
    )
    assert first.response_content_sha256 != changed.response_content_sha256
    payload = first.model_dump(mode="json")
    reordered = {key: payload[key] for key in reversed(list(payload))}
    assert first.response_content_sha256 == application._content_hash(
        application._response_hash_payload(
            PredictionServiceRequest.model_validate(_request(manifest)),
            payload["predictions"],
            payload["skipped"],
        )
    )
    assert set(reordered) == set(payload)


def test_service_error_is_safe_and_does_not_contain_paths_or_secrets() -> None:
    error = PredictionServiceError(
        "blocked_provenance",
        "request could not be verified",
        provenance_details={"expected": "fingerprint", "matched": False},
    )
    payload = error.as_dict()
    assert not any(str(value).startswith("/") for value in payload.values())
    assert "secret" not in json.dumps(payload).lower()
