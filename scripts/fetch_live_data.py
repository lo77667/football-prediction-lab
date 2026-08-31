#!/usr/bin/env python3
"""Fetch real provider data into a content-addressed raw archive.

Required environment variables are read only at runtime and are never written
into metadata. This command is read-only and does not expose betting actions.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from football_prediction_lab.source.football_data_org import FootballDataOrgClient
from football_prediction_lab.source.raw_archive import RawArchive
from football_prediction_lab.source.rss import RSSClient
from football_prediction_lab.source.the_odds_api import TheOddsApiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch read-only football data into a raw archive")
    parser.add_argument("--archive", type=Path, default=Path("data/raw"))
    parser.add_argument("--competition", default="PL")
    parser.add_argument("--odds-sport", default="soccer_epl")
    parser.add_argument("--rss-url")
    parser.add_argument("--skip-football-data", action="store_true")
    parser.add_argument("--skip-odds", action="store_true")
    args = parser.parse_args()
    archive = RawArchive(args.archive)
    if not args.skip_football_data:
        token = os.environ.get("FOOTBALL_DATA_API_TOKEN")
        if not token:
            parser.error("FOOTBALL_DATA_API_TOKEN is required unless --skip-football-data is used")
        response = FootballDataOrgClient(token).fetch_matches(args.competition)
        archive.store(
            provider="football-data.org",
            endpoint=response.endpoint,
            payload=_json_bytes(response.payload),
            fetched_at_utc=response.fetched_at_utc,
            extra_metadata={"response_sha256": response.response_sha256},
        )
    if not args.skip_odds:
        key = os.environ.get("THE_ODDS_API_KEY")
        if not key:
            parser.error("THE_ODDS_API_KEY is required unless --skip-odds is used")
        response = TheOddsApiClient(key).fetch_odds(args.odds_sport)
        archive.store(
            provider="the-odds-api",
            endpoint=response.endpoint,
            payload=_json_bytes(response.payload),
            fetched_at_utc=response.fetched_at_utc,
            extra_metadata={"response_sha256": response.response_sha256},
        )
    if args.rss_url:
        response, raw_payload = RSSClient(allow_network=True).fetch_raw(args.rss_url)
        archive.store(
            provider="rss",
            endpoint=response.feed_url,
            payload=raw_payload,
            fetched_at_utc=response.fetched_at_utc,
            extra_metadata={
                "response_sha256": response.response_sha256,
                "parsed_items": len(response.items),
            },
        )
    return 0


def _json_bytes(value: object) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
