"""Index current and historical atomic Cycle 41.1 service runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.service.artifact_validation import sha256_file, validate_service_run

REQUIRED_FILES = (
    "service_request.json",
    "service_response.json",
    "service_manifest.json",
    "shadow_ledger.jsonl",
    "predictions_prelabel.jsonl",
    "validation.json",
)


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def index_runs(root: Path, output_path: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError("service artifact root is missing")
    run_dirs = sorted(
        path for path in root.iterdir() if path.is_dir() and path.name != "historical"
    )
    if len(run_dirs) != 1:
        raise ValueError("artifact root must contain exactly one current run")
    active_run = run_dirs[0]
    validation = validate_service_run(active_run)
    manifest = json.loads((active_run / "service_manifest.json").read_text(encoding="utf-8"))
    artifacts = []
    for name in REQUIRED_FILES:
        path = active_run / name
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"missing artifact: {name}")
        artifacts.append(
            {
                "path": _relative(root.parent if root.name == "runs" else root, path),
                "sha256": sha256_file(path),
                "generation_status": "current",
                "source_commit": manifest["code_commit"],
                "current": True,
            }
        )
    payload = {
        "schema_version": "cycle41-1-artifact-index-v1",
        "active_run_fingerprint": active_run.name,
        "active_run_relative_path": _relative(
            root.parent if root.name == "runs" else root, active_run
        ),
        "source_commit": manifest["code_commit"],
        "request_fingerprint": manifest["request_fingerprint"],
        "generation_status": "current",
        "historical_runs": [],
        "artifacts": artifacts,
        "validation": validation,
        "commercial_release": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(index_runs(args.root, args.output), ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
