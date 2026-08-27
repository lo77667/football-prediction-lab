"""Run one deterministic local CSV ingestion with audit outputs."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SRC))  # noqa: E402

from football_prediction_lab.ingestion.local_csv import ingest_file  # noqa: E402


def source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    marker = ROOT / "SOURCE_COMMIT.txt"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="authorized local CSV path")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="data/cycle38")
    parser.add_argument("--source-name", default="authorized_local_csv")
    parser.add_argument("--source-version", default="local-file-v1")
    parser.add_argument(
        "--license-or-usage-policy",
        default="user-authorized-local-file; verify before redistribution",
    )
    parser.add_argument("--source-timezone")
    parser.add_argument("--season", default="unknown")
    parser.add_argument("--competition", default="unknown")
    parser.add_argument("--max-rejection-rate", type=float, default=0.25)
    args = parser.parse_args()
    result = ingest_file(
        Path(args.input),
        run_id=args.run_id,
        output_root=Path(args.output_root),
        source_name=args.source_name,
        source_version=args.source_version,
        license_or_usage_policy=args.license_or_usage_policy,
        source_timezone=args.source_timezone,
        season=args.season,
        competition=args.competition,
        code_commit=source_commit(),
        max_rejection_rate=args.max_rejection_rate,
    )
    print(f"manifest_path={result.manifest_path}")
    print(f"normalized_path={result.normalized_path}")
    print(f"quarantine_path={result.quarantine_path}")
    print(f"raw_path={result.raw_path}")
    print(f"rows_read={result.manifest['run']['rows_read']}")
    print(f"rows_accepted={result.manifest['run']['rows_accepted']}")
    print(f"rows_quarantined={result.manifest['run']['rows_quarantined']}")
    print(f"status={result.manifest['run']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
