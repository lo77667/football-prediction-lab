"""Provenance helpers for generated normalized and feature files."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_identity_columns_match(
    input_frame: pd.DataFrame,
    output_frame: pd.DataFrame,
    *,
    id_column: str = "match_id",
    time_column: str = "kickoff_utc",
) -> None:
    """Raise when output identity or timestamp rows differ from sorted input."""

    required = [id_column, time_column]
    if any(column not in input_frame.columns for column in required):
        raise ValueError(f"Input lacks identity columns: {required}")
    if any(column not in output_frame.columns for column in required):
        raise ValueError(f"Output lacks identity columns: {required}")
    left = input_frame[required].copy()
    right = output_frame[required].copy()
    left[time_column] = pd.to_datetime(left[time_column], utc=True, errors="raise")
    right[time_column] = pd.to_datetime(right[time_column], utc=True, errors="raise")
    left = left.sort_values([time_column, id_column]).reset_index(drop=True)
    right = right.reset_index(drop=True)
    if not left.equals(right):
        raise ValueError("Output match_id/kickoff_utc does not match sorted input")


def build_manifest(
    *,
    input_path: str,
    input_sha256: str,
    output_path: str,
    rows_before: int,
    rows_after: int,
    frame: pd.DataFrame,
    feature_version: str,
) -> dict[str, Any]:
    """Build JSON-safe metadata for a generated file."""

    timestamps = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce")
    return {
        "input_path": input_path,
        "input_sha256": input_sha256,
        "output_path": output_path,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "kickoff_utc_min": None if timestamps.empty else str(timestamps.min()),
        "kickoff_utc_max": None if timestamps.empty else str(timestamps.max()),
        "timezone": "UTC",
        "feature_version": feature_version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write an indented UTF-8 manifest without secrets."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
