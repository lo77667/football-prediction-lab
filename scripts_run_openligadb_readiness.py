"""Probe OpenLigaDB coverage with an explicit network opt-in."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.source import OpenLigaDBClient, OpenLigaDBError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league-shortcut", default="pl")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/generated/openligadb_readiness.json"),
    )
    args = parser.parse_args()
    report: dict[str, object] = {
        "provider": "OpenLigaDB",
        "endpoint": f"https://api.openligadb.de/getmatchdata/{args.league_shortcut}/{args.season}",
        "league_shortcut": args.league_shortcut,
        "season": args.season,
        "network_opt_in": args.allow_network,
        "status": "deferred_network_disabled",
        "match_count": 0,
        "upcoming_count": 0,
        "finished_count": 0,
        "response_sha256": None,
        "fetched_at_utc": None,
        "from_cache": False,
        "commercial_release": False,
    }
    if args.allow_network:
        try:
            batch = OpenLigaDBClient(allow_network=True).fetch_league_season(
                args.league_shortcut,
                args.season,
            )
        except (OpenLigaDBError, ValueError) as error:
            report["status"] = "error"
            report["error_type"] = type(error).__name__
            report["error_message"] = str(error)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 1
        now = datetime.now(UTC)
        report.update(
            {
                "status": "live_probe_passed",
                "match_count": len(batch.matches),
                "upcoming_count": sum(not match.finished for match in batch.matches),
                "finished_count": sum(match.finished for match in batch.matches),
                "response_sha256": batch.response_sha256,
                "fetched_at_utc": now.isoformat().replace("+00:00", "Z"),
                "from_cache": batch.from_cache,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
