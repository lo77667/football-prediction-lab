"""Verify Cycle 36 reproducibility from the current project root."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("$", " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> int:
    root_text = str(PROJECT_ROOT.resolve())
    import football_prediction_lab
    import football_prediction_lab.evaluation.cycle36_model_selection as selection

    package_path = Path(football_prediction_lab.__file__).resolve()
    selection_path = Path(selection.__file__).resolve()
    for label, path in (("package", package_path), ("selection", selection_path)):
        print(f"{label}_path={path}")
        if not str(path).startswith(root_text):
            raise RuntimeError(f"{label} import escaped project root: {path}")
    print(f"python={sys.version.split()[0]}")
    run([sys.executable, "-m", "pytest", "-q"])
    run(["ruff", "check", "."])
    run([sys.executable, "-m", "compileall", "-q", "src", "scripts"])
    run([sys.executable, "scripts_test_summary.py"])
    print("cycle36_reproducibility=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
