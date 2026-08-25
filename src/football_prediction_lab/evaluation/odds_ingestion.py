"""Provider-neutral local ingestion for provenance-first odds snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from football_prediction_lab.data.provenance import sha256_file, write_manifest
from football_prediction_lab.evaluation.odds_quality import profile_odds_quality
from football_prediction_lab.evaluation.odds_schema import MatchReference, OddsSnapshot


class IngestionManifest(BaseModel):
    """Metadata-only record describing a local ingestion attempt."""

    model_config = ConfigDict(extra="forbid")

    input_path: str
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_name: str
    source_version: str
    license_status: str
    rows_read: int = Field(ge=0)
    rows_valid: int = Field(ge=0)
    rows_rejected: int = Field(ge=0)
    rejected_by_reason: dict[str, int]
    protected_holdout_rows: int = Field(ge=0)
    quality_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_duplicate_identity_rows: int = Field(ge=0)
    quality_non_monotonic_match_captures: int = Field(ge=0)


def ingest_jsonl_snapshots(
    path: Path,
    *,
    source_name: str,
    source_version: str,
    license_status: str,
    reusable: bool,
    matches: list[MatchReference],
    manifest_path: Path | None = None,
    protected_seasons: set[str] | None = None,
) -> tuple[list[OddsSnapshot], IngestionManifest]:
    """Read only local JSONL; enrich missing file hash and fail closed on policy/holdout."""

    if not source_name.strip() or not source_version.strip() or not license_status.strip():
        raise ValueError("source_name, source_version, and license_status are required")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    file_hash = sha256_file(path)
    match_seasons = {match.match_id: match.season for match in matches}
    protected = protected_seasons or {"2526"}
    accepted: list[OddsSnapshot] = []
    reasons: dict[str, int] = {}
    rows_read = 0
    protected_count = 0

    def reject(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            rows_read += 1
            try:
                payload: dict[str, Any] = json.loads(line)
                if not reusable:
                    reject("source_not_reusable")
                    continue
                match_id = str(payload.get("match_id", ""))
                if match_seasons.get(match_id) in protected:
                    protected_count += 1
                    reject("protected_holdout_season")
                    continue
                payload.setdefault("input_sha256", file_hash)
                payload.setdefault("source_name", source_name)
                payload.setdefault("source_version", source_version)
                snapshot = OddsSnapshot.model_validate(payload)
                if snapshot.source_name != source_name or snapshot.source_version != source_version:
                    reject("source_metadata_mismatch")
                    continue
                accepted.append(snapshot)
            except Exception as error:
                reject(f"invalid_row:{type(error).__name__}")
                continue

    quality = profile_odds_quality(accepted)
    manifest = IngestionManifest(
        input_path=str(path),
        input_sha256=file_hash,
        source_name=source_name,
        source_version=source_version,
        license_status=license_status,
        rows_read=rows_read,
        rows_valid=len(accepted),
        rows_rejected=sum(reasons.values()),
        rejected_by_reason=dict(sorted(reasons.items())),
        protected_holdout_rows=protected_count,
        quality_profile_sha256=quality.profile_sha256,
        quality_duplicate_identity_rows=quality.duplicate_identity_rows,
        quality_non_monotonic_match_captures=quality.non_monotonic_match_captures,
    )
    if manifest_path is not None:
        write_manifest(manifest.model_dump(mode="json"), manifest_path)
    return accepted, manifest
