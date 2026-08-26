"""Audit external-source readiness without contacting unconfigured providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.ingestion.external_readiness import (
    deferred_readiness_report,
    load_external_policy,
    write_readiness_report,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / "configs" / "cycle40_external_source_policy.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "generated" / "cycle_40_source_readiness.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["readiness"], default="readiness")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    policy = load_external_policy(args.policy)
    report = deferred_readiness_report(policy, policy_path=args.policy)
    report_sha256 = write_readiness_report(report, args.output)
    print(f"external_source_status={report['external_source_status']}")
    print(f"source_status={report['source_status']}")
    print(f"verified_snapshots={report['valid_rows']}")
    print(f"benchmark_status={report['benchmark_status']}")
    print(f"commercial_release={str(report['commercial_release']).lower()}")
    print(f"report_path={args.output.resolve()}")
    print(f"report_sha256={report_sha256}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
