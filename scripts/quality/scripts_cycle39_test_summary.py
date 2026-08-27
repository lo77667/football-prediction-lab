"""Generate the executable pytest summary artifact for Cycle 39."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_pytest(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def _count(pattern: str, output: str, label: str) -> int:
    match = re.search(pattern, output)
    if match is None:
        raise RuntimeError(f"pytest output did not contain {label}")
    return int(match.group("count"))


def _tool_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "generated" / "cycle_39_test_summary.json",
    )
    args = parser.parse_args()
    collected_output = _run_pytest("--collect-only")
    execution_output = _run_pytest()
    summary = {
        "schema_version": "cycle39-pytest-summary-v1",
        "collected_count": _count(
            r"(?P<count>\d+) tests? collected", collected_output, "collected count"
        ),
        "passed_count": _count(r"(?P<count>\d+) passed", execution_output, "passed count"),
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "tool_versions": {
            "python": sys.version.split()[0],
            "pytest": _tool_version("pytest"),
            "ruff": _tool_version("ruff"),
        },
    }
    if summary["collected_count"] != summary["passed_count"]:
        raise RuntimeError("collected_count and passed_count differ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
