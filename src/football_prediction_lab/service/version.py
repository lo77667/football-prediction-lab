"""Version metadata for the local Prediction Service Core."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

SERVICE_VERSION = "cycle41-prediction-service-v1"
POLICY_VERSION = "cycle36-future-2627-policy-v1"
MODEL_VERSION = "cycle36-candidate-suite-v1"
FEATURE_VERSION = "cycle39-shadow-input-v1"


def code_commit(root: Path | None = None) -> str:
    """Resolve commit from Git or the archive marker without exposing a path."""

    working_root = root or Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=working_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    marker = working_root / "SOURCE_COMMIT.txt"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
            return value
    return "unknown"


def version_payload(root: Path | None = None) -> dict[str, Any]:
    return {
        "service_version": SERVICE_VERSION,
        "code_commit": code_commit(root),
        "policy_version": POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "commercial_release": False,
    }
