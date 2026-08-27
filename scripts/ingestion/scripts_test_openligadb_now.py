"""Fetch and validate one OpenLigaDB Premier League snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.source import OpenLigaDBClient, OpenLigaDBError

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--league", default="pl")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    if not args.allow_network:
        print(
            json.dumps(
                {
                    "status": "deferred_network_disabled",
                    "message": "أضف --allow-network لاختبار المصدر العام الآن.",
                    "commercial_release": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0

    try:
        batch = OpenLigaDBClient(
            allow_network=True,
            timeout_seconds=args.timeout,
            min_interval_seconds=1.0,
        ).fetch_league_season(args.league, args.season)
    except (OpenLigaDBError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "commercial_release": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 1

    match_ids = [match.match_id for match in batch.matches]
    valid_utc = all(
        match.kickoff_utc.tzinfo is not None
        and match.kickoff_utc.utcoffset() == datetime.min.replace(tzinfo=UTC).utcoffset()
        for match in batch.matches
    )
    valid_identity = all(
        match.league_shortcut == args.league and match.league_season == args.season
        for match in batch.matches
    )
    unique_ids = len(match_ids) == len(set(match_ids))
    finished = sum(match.finished for match in batch.matches)
    upcoming = len(batch.matches) - finished
    checks_passed = bool(batch.matches) and valid_utc and valid_identity and unique_ids
    summary = {
        "status": "passed" if checks_passed else "failed_validation",
        "provider": "OpenLigaDB",
        "endpoint": batch.endpoint,
        "league_shortcut": args.league,
        "season": args.season,
        "match_count": len(batch.matches),
        "finished_count": finished,
        "upcoming_count": upcoming,
        "unique_match_ids": unique_ids,
        "explicit_utc_timestamps": valid_utc,
        "league_and_season_match": valid_identity,
        "response_sha256": batch.response_sha256,
        "fetched_at_utc": batch.fetched_at_utc.isoformat().replace("+00:00", "Z"),
        "raw_payload_saved": False,
        "network_opt_in": True,
        "commercial_release": False,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
