"""Serve the Cycle 42 prediction adapter on loopback only."""

from __future__ import annotations

import argparse
from pathlib import Path

from football_prediction_lab.service.application import PredictionApplication
from football_prediction_lab.service.local_api import LocalAPIHTTPServer, LocalServiceAPI

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "configs" / "cycle36_future_holdout_policy.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-path", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--allowed-manifest-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--readiness-run-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    application = PredictionApplication(
        policy_path=args.policy_path,
        allowed_manifest_root=args.allowed_manifest_root,
        output_root=args.output_root,
        code_root=ROOT,
    )
    api = LocalServiceAPI(
        application,
        readiness_run_dir=args.readiness_run_dir,
        audit_path=args.output_root / "audit.jsonl",
    )
    server = LocalAPIHTTPServer(api, host=args.host, port=args.port)
    print(f"local API listening on {server.server_address[0]}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
