"""Fail-closed source selection for commercial evaluation inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from football_prediction_lab.data.provenance import sha256_file

REQUIRED_MANIFEST_FIELDS = {
    "input_sha256",
    "feature_version",
    "first_datetime",
    "last_datetime",
}


def select_manifested_source_files(
    paths: list[Path], *, protected_seasons: set[str] | None = None
) -> dict[str, Any]:
    """Select only files with auditable manifests; never select protected seasons."""

    protected = protected_seasons or {"2526"}
    selected: list[str] = []
    rejected: list[dict[str, str]] = []
    for path in sorted(paths):
        if any(season in path.name for season in protected):
            rejected.append({"path": str(path), "reason": "protected_season"})
            continue
        manifest_path = Path(f"{path}.manifest.json")
        if not manifest_path.exists():
            rejected.append({"path": str(path), "reason": "missing_manifest"})
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rejected.append({"path": str(path), "reason": "invalid_manifest"})
            continue
        missing = sorted(REQUIRED_MANIFEST_FIELDS.difference(manifest))
        if missing:
            rejected.append({"path": str(path), "reason": f"manifest_missing:{','.join(missing)}"})
            continue
        if manifest.get("license_policy") not in {"redistributable", "internal_licensed"}:
            rejected.append({"path": str(path), "reason": "unverified_license_policy"})
            continue
        try:
            actual_sha256 = sha256_file(path)
        except OSError:
            rejected.append({"path": str(path), "reason": "unreadable_source"})
            continue
        if manifest.get("input_sha256") != actual_sha256:
            rejected.append({"path": str(path), "reason": "input_sha256_mismatch"})
            continue
        if not manifest.get("first_datetime") or not manifest.get("last_datetime"):
            rejected.append({"path": str(path), "reason": "missing_datetime_range"})
            continue
        selected.append(str(path))
    return {
        "selected_files": selected,
        "rejected_files": rejected,
        "selection_status": "eligible" if selected else "no_go",
        "protected_seasons": sorted(protected),
        "economic_claim_status": "not_assessed",
    }
