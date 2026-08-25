"""Apply the paired-bootstrap uncertainty gate to a saved report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.learning.retraining import decide_paired_uncertainty_retraining


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    report = json.loads((root / args.input).read_text(encoding="utf-8"))
    summary = report["uncertainty"] | {
        "folds": report["folds"],
        "rows": report["rows"],
    }
    decision = decide_paired_uncertainty_retraining(summary)
    result = {
        "input": args.input,
        "candidate": report["candidate"],
        "baseline": report["baseline"],
        "accepted": decision.accepted,
        "reason": decision.reason,
        "uncertainty": report["uncertainty"],
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"output_path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
