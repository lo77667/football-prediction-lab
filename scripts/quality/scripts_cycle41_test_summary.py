"""Generate an auditable pytest summary for Cycle 41."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports" / "generated" / "cycle_41_test_summary.json"
SUMMARY_PATTERN = re.compile(
    r"(?P<count>\d+) (?:passed|failed|skipped|xfailed|xpassed|error|errors)"
)


def _run_pytest(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def _parse_collected(output: str) -> int:
    match = re.search(r"(?P<count>\d+) tests? collected", output)
    if match is None:
        raise RuntimeError("pytest collect-only output did not contain a collected count")
    return int(match.group("count"))


def _parse_passed(output: str) -> int:
    if not SUMMARY_PATTERN.search(output):
        raise RuntimeError("pytest output did not contain a test summary")
    match = re.search(r"(?P<count>\d+) passed", output)
    if match is None:
        raise RuntimeError("pytest output did not contain a passed count")
    return int(match.group("count"))


def _source_revision() -> str:
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


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def main() -> None:
    collected_output = _run_pytest("--collect-only")
    execution_output = _run_pytest()
    summary = {
        "schema_version": "cycle41-pytest-summary-v1",
        "collected_count": _parse_collected(collected_output),
        "passed_count": _parse_passed(execution_output),
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit": _source_revision(),
        "tool_versions": {
            "python": sys.version.split()[0],
            "pytest": _version("pytest"),
            "ruff": _version("ruff"),
        },
    }
    if summary["collected_count"] != summary["passed_count"]:
        raise RuntimeError("collected_count and passed_count differ")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
