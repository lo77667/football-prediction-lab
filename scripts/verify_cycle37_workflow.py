"""Static checks for the Cycle 37 GitHub Actions quality gate."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/quality-gate.yml"
REQUIRED_RUNS = (
    "python -m pip install --upgrade pip",
    "python -m pip install -r requirements.lock",
    "python -m pip install -e '.[dev]'",
    "import football_prediction_lab",
    "python -m pytest -q",
    "ruff check .",
    "python -m compileall -q src scripts",
)


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on", workflow.get(True, {}))
    assert {"push", "pull_request", "workflow_dispatch"} <= set(triggers)
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert "continue-on-error" not in text
    assert "secrets" not in text
    jobs = workflow["jobs"]
    job = jobs["test-and-lint"]
    assert job["strategy"]["matrix"]["python-version"] == ["3.11", "3.12"]
    assert len(job["steps"]) >= 8
    action_uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert action_uses == ["actions/checkout@v4", "actions/setup-python@v5"]
    run_text = "\n".join(step.get("run", "") for step in job["steps"])
    for required in REQUIRED_RUNS:
        assert required in run_text, f"missing required command: {required}"
    assert not re.search(r"uses:\s+[^\n]+/[^\n]+\.ya?ml@", text)
    print("cycle37_workflow_static_check=passed")
    print(f"workflow={WORKFLOW}")
    print(f"jobs={len(jobs)} steps={len(job['steps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
