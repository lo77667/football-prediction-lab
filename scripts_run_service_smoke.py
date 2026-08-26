"""Run a local Cycle 41 Prediction Service smoke flow without network access."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from football_prediction_lab.ingestion.local_csv import ingest_file  # noqa: E402
from football_prediction_lab.service.application import PredictionApplication  # noqa: E402
from football_prediction_lab.service.contracts import PredictionServiceRequest  # noqa: E402
from football_prediction_lab.service.version import (  # noqa: E402
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    code_commit,
)

FIXTURE = ROOT / "tests" / "fixtures" / "cycle39_shadow" / "processed_with_frozen_probabilities.csv"
POLICY = ROOT / "configs" / "cycle36_future_holdout_policy.json"
DEFAULT_OUTPUT = ROOT / "reports" / "generated" / "cycle_41_service_smoke"


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of_utc must include an explicit timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--as-of", type=_parse_datetime, default=_parse_datetime("2025-01-01T12:00:00Z")
    )
    parser.add_argument("--market", choices=["btts", "cards"], default="btts")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    ingestion_root = output_root / "ingestion"
    commit = code_commit(ROOT)
    ingestion = ingest_file(
        FIXTURE,
        run_id="cycle41-service-input",
        output_root=ingestion_root,
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
        allowed_manifest_root=ingestion_root,
        output_root=output_root,
        code_root=ROOT,
    )
    request = PredictionServiceRequest.model_validate(
        {
            "request_id": "cycle41-smoke",
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
    response_path = output_root / "service_response.json"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (output_root / "service_version.json").write_text(
        json.dumps(application.version(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "service_health.json").write_text(
        json.dumps(
            application.health(ingestion.manifest_path),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"manifest_fingerprint={ingestion.manifest['manifest_fingerprint']}")
    print(f"request_fingerprint={application.request_fingerprint(request)}")
    print(f"response_path={response_path}")
    print(f"response_content_sha256={response.response_content_sha256}")
    print(f"predictions_issued={len(response.predictions)}")
    print(f"skipped_items={len(response.skipped)}")
    print("commercial_release=false")
    print("network_calls=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
