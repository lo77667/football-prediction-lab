#!/usr/bin/env python3
"""scripts/harvest_all.py

Small CLI to run a simple daily harvest pipeline:
- init DB
- harvest RSS injury/suspension feeds
- fetch today's matches from Football-Data.org and cache them
- attempt to fetch Understat xG for each match (best-effort)

Notes:
- This script uses the modules under data_harvester/ which must exist in PYTHONPATH (run from repo root)  # noqa: E501
- It respects the retry/backoff behavior in data_harvester.utils
- It does not use any paid keys. Optionally set FOOTBALL_DATA_API_KEY env var for higher rate limits.  # noqa: E501

Usage:
  python scripts/harvest_all.py --date 2026-09-05 --feeds "feed1,feed2" --only-rss

"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# Ensure repo root is on path so data_harvester can be imported when running from scripts/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import requests  # noqa: E402
from data_harvester import (  # noqa: E402
    db,
    football_data_org,
    rss_harvester,
    understat_harvester,
    utils,
)

logger = utils.get_logger(__name__)

DEFAULT_FEEDS = [
    "http://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040",
    "https://www.goal.com/en/feeds/news",
]

API_BASE = "https://api.football-data.org/v4"
API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")


def parse_args():
    p = argparse.ArgumentParser(
        description="Harvest RSS, Football-Data matches, and Understat xG (best-effort)"
    )
    p.add_argument("--date", help="Date for matches (YYYY-MM-DD). Default: today UTC", default=None)
    p.add_argument(
        "--feeds", help="Comma-separated RSS feeds to harvest", default=",".join(DEFAULT_FEEDS)
    )
    p.add_argument("--only-rss", help="Only run RSS harvest and exit", action="store_true")
    p.add_argument(
        "--limit", help="Limit number of matches to process (for testing)", type=int, default=0
    )
    return p.parse_args()


@utils.retry(exceptions=(requests.RequestException, Exception), tries=3)
def fetch_matches_for_date(date_str: str) -> list[dict]:
    """Fetch matches for date via Football-Data.org /matches?dateFrom=...&dateTo=..."""
    headers = {}
    if API_KEY:
        headers["X-Auth-Token"] = API_KEY
    params = {"dateFrom": date_str, "dateTo": date_str}
    url = f"{API_BASE}/matches"
    logger.info("Fetching matches for %s from Football-Data.org", date_str)
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    # payload typically has 'matches'
    matches = payload.get("matches") or []
    return matches


def main():
    args = parse_args()
    target_date = args.date or datetime.utcnow().strftime("%Y-%m-%d")
    feeds = [f.strip() for f in args.feeds.split(",") if f.strip()]

    # Init DB
    db.init_db()
    logger.info("Database initialized or already exists")

    # 1) RSS harvest
    try:
        logger.info("Starting RSS harvest for %d feeds", len(feeds))
        rss_harvester.harvest_feeds(feeds)
    except Exception as exc:
        logger.exception("RSS harvest failed: %s", exc)

    if args.only_rss:
        logger.info("--only-rss specified, exiting after RSS harvest")
        print("Done: RSS harvest only")
        return

    # 2) Fetch matches list for date
    try:
        matches = fetch_matches_for_date(target_date)
    except Exception as exc:
        logger.exception("Failed to fetch matches list for %s: %s", target_date, exc)
        matches = []

    if not matches:
        logger.info("No matches found for %s, exiting", target_date)
        print(f"No matches found for {target_date}")
        return

    logger.info("Found %d matches for %s", len(matches), target_date)

    # 3) Process matches
    limit = args.limit or 0
    count = 0
    for m in matches:
        if limit and count >= limit:
            break
        try:
            # Extract primary fields
            m_id = str(m.get("id") or m.get("matchId") or "")
            m.get("utcDate") or m.get("date")
            home = (
                (m.get("homeTeam") or {}).get("name")
                if m.get("homeTeam")
                else m.get("homeTeam") or m.get("home_team")
            )
            away = (
                (m.get("awayTeam") or {}).get("name")
                if m.get("awayTeam")
                else m.get("awayTeam") or m.get("away_team")
            )

            # Upsert via the provided module (this will cache in SQLite)
            football_data_org.fetch_match(m_id)
            logger.info("Cached match %s: %s vs %s", m_id, home, away)

            # Attempt Understat fetch (best-effort). Understat IDs differ from football-data IDs; try with m_id anyway  # noqa: E501
            try:
                if hasattr(understat_harvester, "fetch_match_xg"):
                    understat_harvester.fetch_match_xg(m_id)
                    logger.info("Understat fetch returned for match %s", m_id)
                else:
                    logger.warning("Understat harvester not available")
            except Exception as uexc:
                logger.exception("Understat fetch failed for match %s: %s", m_id, uexc)

            count += 1
        except Exception as exc:
            logger.exception("Failed processing match entry: %s", exc)

    print(f"Processed {count} matches for {target_date}")
    logger.info("Harvest run complete: processed %d matches", count)


if __name__ == "__main__":
    main()
