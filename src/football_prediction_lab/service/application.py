"""Application layer for the local, prelabel Prediction Service Core."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from football_prediction_lab.ingestion.local_csv import validate_manifest
from football_prediction_lab.service.artifact_validation import validate_service_run
from football_prediction_lab.service.contracts import (
    PredictionServiceRequest,
    PredictionServiceResponse,
    ServiceOperationalMetrics,
)
from football_prediction_lab.service.errors import (
    ContractMismatch,
    InvalidServiceRequest,
    ManifestPathRejected,
    PredictionServiceError,
    ProvenanceBlocked,
)
from football_prediction_lab.service.version import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
    SERVICE_VERSION,
    code_commit,
    version_payload,
)
from football_prediction_lab.shadow.ledger import ShadowLedger
from football_prediction_lab.shadow.runner import run_shadow


class PredictionApplication:
    """Local application service; transport adapters must call this class."""

    def __init__(
        self,
        *,
        policy_path: Path,
        allowed_manifest_root: Path,
        output_root: Path,
        code_root: Path | None = None,
    ) -> None:
        self.policy_path = policy_path.resolve()
        self.allowed_manifest_root = allowed_manifest_root.resolve()
        self.output_root = output_root.resolve()
        self.code_root = (code_root or Path(__file__).resolve().parents[3]).resolve()

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    @classmethod
    def _content_hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical_json(value)).hexdigest()

    def _safe_manifest_path(self, path: Path) -> Path:
        candidate = path.resolve()
        try:
            candidate.relative_to(self.allowed_manifest_root)
        except ValueError as exc:
            raise ManifestPathRejected() from exc
        if candidate == self.allowed_manifest_root:
            raise ManifestPathRejected()
        return candidate

    def _verified_manifest(self, path: Path, expected_fingerprint: str) -> dict[str, Any]:
        manifest_path = self._safe_manifest_path(path)
        try:
            manifest = validate_manifest(manifest_path)
        except Exception as exc:
            raise ProvenanceBlocked() from exc
        if manifest.get("manifest_fingerprint") != expected_fingerprint:
            raise ContractMismatch("manifest_fingerprint")
        for key in (
            "output_path",
            "processed_output_path",
            "raw_path",
            "quarantine_path",
            "manifest_path",
        ):
            referenced = manifest.get(key)
            if referenced is None:
                continue
            try:
                Path(str(referenced)).resolve().relative_to(self.allowed_manifest_root)
            except ValueError as exc:
                raise ManifestPathRejected() from exc
        return manifest

    def _validate_request(self, request: PredictionServiceRequest) -> None:
        if request.policy_version != POLICY_VERSION:
            raise ContractMismatch("policy_version")
        if request.model_version != MODEL_VERSION:
            raise ContractMismatch("model_version")
        if request.feature_version != FEATURE_VERSION:
            raise ContractMismatch("feature_version")
        actual_commit = code_commit(self.code_root)
        if request.expected_source_commit != actual_commit:
            raise ContractMismatch("expected_source_commit")

    def _preflight_timing(
        self, manifest: dict[str, Any], request: PredictionServiceRequest
    ) -> None:
        frame = pd.read_csv(Path(manifest["processed_output_path"]))
        if "kickoff_utc" not in frame.columns:
            raise ProvenanceBlocked()
        kickoff = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce")
        if kickoff.isna().any():
            raise ProvenanceBlocked()
        if (kickoff <= request.as_of_utc).any():
            raise InvalidServiceRequest("as_of_utc must precede kickoff_utc", field="as_of_utc")
        for column in ("probability_btts", "probability_cards"):
            if column in frame.columns:
                probabilities = pd.to_numeric(frame[column], errors="coerce")
                if probabilities.isna().any() or ((probabilities < 0) | (probabilities > 1)).any():
                    raise InvalidServiceRequest(
                        "verified probability is outside [0,1]", field=column
                    )

    @classmethod
    def request_fingerprint(cls, request: PredictionServiceRequest) -> str:
        """Hash semantic request content; request_id is transport metadata only."""

        semantic = request.model_dump(mode="json", exclude={"request_id"})
        return cls._content_hash(semantic)

    @classmethod
    def _run_id(cls, request: PredictionServiceRequest) -> str:
        return f"service-{cls.request_fingerprint(request)[:40]}"

    def _response_hash_payload(
        self,
        request: PredictionServiceRequest,
        predictions: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        stable_metrics = {
            key: value for key, value in metrics.items() if key != "idempotent_replay"
        }
        return {
            "request_fingerprint": self.request_fingerprint(request),
            "code_commit": code_commit(self.code_root),
            "service_version": SERVICE_VERSION,
            "policy_version": request.policy_version,
            "model_version": request.model_version,
            "feature_version": request.feature_version,
            "manifest_fingerprint": request.manifest_fingerprint,
            "as_of_utc": request.as_of_utc.isoformat(),
            "predictions": predictions,
            "skipped": skipped,
            "operational_metrics": stable_metrics,
        }

    def predict(self, request: PredictionServiceRequest) -> PredictionServiceResponse:
        """Verify provenance and issue a prelabel response through the Shadow Runner."""

        self._validate_request(request)
        manifest_path = self._manifest_path_for_fingerprint(request.manifest_fingerprint)
        manifest = self._verified_manifest(manifest_path, request.manifest_fingerprint)
        self._preflight_timing(manifest, request)
        run_id = self._run_id(request)
        predictions_path = self.output_root / "predictions" / f"{run_id}.json"
        was_existing = predictions_path.exists()
        try:
            result = run_shadow(
                manifest_path=manifest_path,
                as_of_utc=request.as_of_utc,
                run_id=run_id,
                output_root=self.output_root,
                policy_path=self.policy_path,
                code_commit=code_commit(self.code_root),
            )
        except PredictionServiceError:
            raise
        except ValueError as exc:
            message = str(exc)
            if "target" in message or "post-match" in message or "probability" in message:
                raise InvalidServiceRequest(
                    "verified manifest or pre-match content is invalid"
                ) from exc
            raise ProvenanceBlocked() from exc
        except Exception as exc:
            raise ProvenanceBlocked() from exc
        artifact = result["artifact"]
        predictions = [
            item for item in artifact["predictions"] if item.get("market") == request.market
        ]
        skipped = sorted(
            artifact["skipped"],
            key=lambda item: (
                str(item.get("match_id", "")),
                str(item.get("market", "")),
                str(item.get("reason", "")),
            ),
        )
        ledger = ShadowLedger(Path(result["ledger_path"]))
        ledger_records = ledger.records()
        ledger_metrics = {
            "predictions_issued": len(predictions),
            "skipped_items": len(skipped),
            "response_predictions_count": len(predictions),
            "ledger_records": len(ledger_records),
            "ledger_events_count": len(ledger_records),
            "ledger_prediction_count": len(ledger_records),
            "ledger_markets": sorted(
                {
                    str(entry["record"].get("market"))
                    for entry in ledger_records
                    if entry.get("record", {}).get("market") in {"btts", "cards"}
                }
            ),
            "ledger_sha256": ledger.sha256(),
            "idempotent_replay": was_existing,
        }
        content_hash = self._content_hash(
            self._response_hash_payload(request, predictions, skipped, ledger_metrics)
        )
        response = PredictionServiceResponse(
            request_id=request.request_id,
            request_fingerprint=self.request_fingerprint(request),
            code_commit=code_commit(self.code_root),
            service_version=SERVICE_VERSION,
            policy_version=request.policy_version,
            model_version=request.model_version,
            feature_version=request.feature_version,
            manifest_fingerprint=request.manifest_fingerprint,
            as_of_utc=request.as_of_utc,
            predictions=predictions,
            skipped=skipped,
            operational_metrics=ServiceOperationalMetrics(**ledger_metrics),
            response_content_sha256=content_hash,
        )
        return response

    def _manifest_path_for_fingerprint(self, fingerprint: str) -> Path:
        candidates = sorted(self.allowed_manifest_root.glob("manifests/*.json"))
        for candidate in candidates:
            try:
                manifest = validate_manifest(candidate)
            except Exception:
                continue
            if manifest.get("manifest_fingerprint") == fingerprint:
                return candidate.resolve()
        raise ProvenanceBlocked()

    def health(self, manifest_path: Path | None = None) -> dict[str, Any]:
        """Return a safe health state; only a verified manifest can be healthy."""

        payload = {
            "status": "not_ready",
            "service_version": SERVICE_VERSION,
            "commercial_release": False,
        }
        if manifest_path is None:
            return payload
        try:
            safe_path = self._safe_manifest_path(manifest_path)
            if not safe_path.is_dir():
                raise ValueError("health requires a complete atomic run directory")
            validate_service_run(safe_path)
        except Exception:
            payload["status"] = "blocked_provenance"
            return payload
        payload["status"] = "healthy"
        return payload

    def version(self) -> dict[str, Any]:
        return version_payload(self.code_root)
