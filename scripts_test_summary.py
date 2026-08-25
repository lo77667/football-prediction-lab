"""Generate an auditable pytest execution summary artifact."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "reports" / "generated" / "cycle_32_test_summary.json"
SUMMARY_PATTERN = re.compile(
    r"(?P<count>\d+) (?:passed|failed|skipped|xfailed|xpassed|error|errors)"
)


def _run_pytest(*args: str) -> str:
    result = subprocess.run(
        ["pytest", "-q", *args],
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
    matches = SUMMARY_PATTERN.findall(output)
    passed = re.search(r"(?P<count>\d+) passed", output)
    if passed is None:
        raise RuntimeError("pytest output did not contain a passed count")
    if not matches:
        raise RuntimeError("pytest output did not contain a test summary")
    return int(passed.group("count"))


def main() -> None:
    collected_output = _run_pytest("--collect-only")
    execution_output = _run_pytest()
    summary = {
        "schema_version": "pytest-summary-v1",
        "collected_count": _parse_collected(collected_output),
        "passed_count": _parse_passed(execution_output),
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
    }
    if summary["collected_count"] != summary["passed_count"]:
        raise RuntimeError("collected_count and passed_count differ")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
