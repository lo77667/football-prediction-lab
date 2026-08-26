"""Audit external-source readiness without contacting unconfigured providers."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.ingestion.external_readiness import (
    build_deferred_manifest,
    deferred_readiness_report,
    load_external_policy,
    validate_deferred_manifest,
    validate_readiness_report,
    write_manifest,
    write_readiness_report,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / "configs" / "cycle40_external_source_policy.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "generated" / "cycle_40_source_readiness.json"
DEFAULT_MANIFEST = ROOT / "reports" / "generated" / "cycle_40_deferred_manifest.json"


def _source_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        marker = ROOT / "SOURCE_COMMIT.txt"
        if marker.exists():
            value = marker.read_text(encoding="utf-8").strip()
            if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
                return value
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["readiness", "validate"], default="readiness")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--input", type=Path, help="Existing report for --mode validate")
    parser.add_argument("--manifest", type=Path, help="Existing manifest for --mode validate")
    args = parser.parse_args()
    policy = load_external_policy(args.policy)
    if args.mode == "validate":
        input_path = args.input or args.output
        report = json.loads(input_path.read_text(encoding="utf-8"))
        result = validate_readiness_report(report, policy)
        if args.manifest or args.manifest_output.exists():
            manifest_path = args.manifest or args.manifest_output
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            result["manifest"] = validate_deferred_manifest(manifest, report, policy)
        print("validation=passed")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    report = deferred_readiness_report(
        policy,
        policy_path=args.policy,
        source_commit=_source_commit(),
        runtime_metadata={
            "report_path": str(args.output.resolve()),
            "output_root": str(args.output.resolve().parent),
            "hostname": socket.gethostname(),
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    )
    report_file_sha256 = write_readiness_report(report, args.output)
    manifest = build_deferred_manifest(report)
    manifest_file_sha256 = write_manifest(manifest, args.manifest_output)
    print(f"external_source_status={report['external_source_status']}")
    print(f"source_status={report['source_status']}")
    print(f"verified_snapshots={report['valid_rows']}")
    print(f"benchmark_status={report['benchmark_status']}")
    print(f"commercial_release={str(report['commercial_release']).lower()}")
    print(f"report_path={args.output.resolve()}")
    print(f"report_content_sha256={report['report_content_sha256']}")
    print(f"report_file_sha256={report_file_sha256}")
    print(f"manifest_path={args.manifest_output.resolve()}")
    print(f"manifest_file_sha256={manifest_file_sha256}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
