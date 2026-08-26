"""Run one atomic local Cycle 41.1 service smoke flow without network access."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.ingestion.local_csv import ingest_file  # noqa: E402
from football_prediction_lab.service.application import PredictionApplication  # noqa: E402
from football_prediction_lab.service.artifact_validation import (  # noqa: E402
    request_fingerprint,
    sha256_file,
    validate_service_run,
)
from football_prediction_lab.service.contracts import PredictionServiceRequest  # noqa: E402
from football_prediction_lab.service.version import (  # noqa: E402
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    code_commit,
)

FIXTURE = ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
POLICY = ROOT / "configs" / "cycle36_future_holdout_policy.json"
DEFAULT_OUTPUT = ROOT / "reports" / "generated" / "cycle_41_1_service_smoke"


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of_utc must include an explicit timezone")
    return parsed.astimezone(UTC)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--as-of", type=_parse_datetime, default=_parse_datetime("2025-01-01T12:00:00Z")
    )
    parser.add_argument("--market", choices=["btts", "cards"], default="btts")
    args = parser.parse_args()
    root = args.output_root.resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    commit = code_commit(ROOT)
    with tempfile.TemporaryDirectory(prefix="cycle41-service-input-") as temporary:
        temporary_root = Path(temporary)
        ingestion = ingest_file(
            FIXTURE,
            run_id="cycle41-service-input",
            output_root=temporary_root / "ingestion",
            source_name="cycle41-test-local",
            source_version="cycle41-test-v1",
            license_or_usage_policy="test-only; no redistribution",
            season="2425",
            competition="EPL",
            code_commit=commit,
            max_rejection_rate=1.0,
        )
        application = PredictionApplication(
            policy_path=POLICY,
            allowed_manifest_root=temporary_root / "ingestion",
            output_root=temporary_root / "runner-output",
            code_root=ROOT,
        )
        request = PredictionServiceRequest.model_validate(
            {
                "request_id": "cycle41-1-smoke",
                "manifest_fingerprint": ingestion.manifest["manifest_fingerprint"],
                "as_of_utc": args.as_of,
                "market": args.market,
                "policy_version": POLICY_VERSION,
                "model_version": MODEL_VERSION,
                "feature_version": FEATURE_VERSION,
                "expected_source_commit": commit,
                "mode": "shadow",
            }
        )
        response = application.predict(request)
        run_fingerprint = request_fingerprint(request)
        run_dir = root / "runs" / run_fingerprint
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        request_path = run_dir / "service_request.json"
        response_path = run_dir / "service_response.json"
        manifest_path = run_dir / "service_manifest.json"
        ledger_path = run_dir / "shadow_ledger.jsonl"
        predictions_path = run_dir / "predictions_prelabel.jsonl"
        validation_path = run_dir / "validation.json"
        _write_json(request_path, request.model_dump(mode="json"))
        _write_json(response_path, response.model_dump(mode="json"))
        runner_result = application.output_root
        runner_prediction_path = (
            runner_result / "predictions" / f"service-{run_fingerprint[:40]}.json"
        )
        runner_run_path = runner_result / "runs" / f"service-{run_fingerprint[:40]}.json"
        runner_ledger_path = runner_result / "ledger" / "predictions.jsonl"
        shutil.copyfile(runner_ledger_path, ledger_path)
        runner_artifact = json.loads(runner_prediction_path.read_text(encoding="utf-8"))
        predictions_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                for item in runner_artifact["predictions"]
            ),
            encoding="utf-8",
        )
        del runner_run_path
        ledger_sha = sha256_file(ledger_path)
        manifest = {
            "schema_version": "cycle41-1-service-run-manifest-v1",
            "run_fingerprint": run_fingerprint,
            "request_fingerprint": run_fingerprint,
            "request_sha256": sha256_file(request_path),
            "response_sha256": sha256_file(response_path),
            "response_content_sha256": response.response_content_sha256,
            "ledger_sha256": ledger_sha,
            "prediction_artifact_sha256": sha256_file(predictions_path),
            "code_commit": response.code_commit,
            "policy_version": response.policy_version,
            "model_version": response.model_version,
            "feature_version": response.feature_version,
            "prediction_feature_versions": sorted(
                {str(item["feature_version"]) for item in runner_artifact["predictions"]}
            ),
            "prediction_model_versions": sorted(
                {str(item["model_version"]) for item in runner_artifact["predictions"]}
            ),
            "source_manifest_fingerprint": response.manifest_fingerprint,
            "as_of_utc": response.as_of_utc.isoformat(),
            "predictions_count": len(runner_artifact["predictions"]),
            "response_predictions_count": len(response.predictions),
            "ledger_records_count": response.operational_metrics.ledger_records,
            "commercial_release": False,
            "generation_status": "current",
        }
        _write_json(manifest_path, manifest)
        validation = validate_service_run(run_dir)
        _write_json(validation_path, validation)
    print(f"run_fingerprint={run_fingerprint}")
    print(f"request_fingerprint={response.request_fingerprint}")
    print(f"run_dir={run_dir}")
    print(f"response_content_sha256={response.response_content_sha256}")
    print(f"response_predictions_count={len(response.predictions)}")
    print(f"ledger_records_count={response.operational_metrics.ledger_records}")
    print(f"ledger_sha256={response.operational_metrics.ledger_sha256}")
    print("commercial_release=false")
    print("network_calls=none")
    print("validation=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
