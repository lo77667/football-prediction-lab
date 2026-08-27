"""Run explicit provider readiness checks without enabling prediction or release paths."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from football_prediction_lab.source import (
    ProviderAuthenticationRequired,
    ProviderError,
    ProviderNetworkDisabled,
    build_enabled_clients,
)

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument(
        "--output", default="reports/generated/provider_readiness.json"
    )
    args = parser.parse_args()
    try:
        requested_date = date.fromisoformat(args.date)
    except ValueError as error:
        parser.error("--date must be YYYY-MM-DD")
        raise AssertionError from error

    clients = build_enabled_clients()
    results: dict[str, dict[str, object]] = {}
    for name, client in sorted(clients.items()):
        result: dict[str, object] = {
            "configured": True,
            "network_requested": args.allow_network,
            "status": "deferred",
        }
        if not args.allow_network:
            results[name] = result
            continue
        client.allow_network = True
        try:
            if name == "openligadb":
                batch = client.fetch_league_season("pl", requested_date.year)
            elif name == "sportscore":
                batch = client.fetch_fixtures(requested_date)
            elif name == "football_data":
                batch = client.fetch_fixtures(requested_date, competition="PL")
            else:
                batch = client.fetch_fixtures(requested_date)
            result.update(
                {
                    "status": "reachable",
                    "provider": batch.provider,
                    "matches": len(batch.matches),
                    "response_sha256": batch.response_sha256,
                }
            )
        except ProviderAuthenticationRequired as error:
            result.update({"status": "missing_credential", "error": str(error)})
        except ProviderNetworkDisabled as error:
            result.update({"status": "network_disabled", "error": str(error)})
        except ProviderError as error:
            result.update({"status": "provider_error", "error": str(error)})
        results[name] = result

    report = {
        "schema_version": "provider-readiness-v1",
        "observed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "requested_date": requested_date.isoformat(),
        "mode": "shadow_only",
        "commercial_release": False,
        "network_requested": args.allow_network,
        "providers": results,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
