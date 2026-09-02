#!/usr/bin/env python3
"""
Example bookmaker scraper (config-driven).

Usage examples:
1) Single URL:
   python scripts/bookmaker_scraper_example.py --match-id M123 --bookie "ExampleBookie" --url "https://example.com/match/..." 

2) Batch from JSON file (list of {"match_id","bookie","url"}):
   python scripts/bookmaker_scraper_example.py --batch jobs.json

Notes:
- This is a configurable extractor: add or tune site_configs for each bookmaker.
- It will call data_harvester.db.insert_market_odds(match_id, bookmaker, market, selection, odds, line)
"""
from __future__ import annotations
import re
import json
import argparse
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# import local modules
from data_harvester import db, utils

logger = utils.get_logger(__name__)

# Minimal site config example: tune selectors for each bookmaker
# For each site you can define CSS selectors or heuristics to find market blocks.
# This example shows two generic approaches:
SITE_CONFIGS = {
    # Example: a site that displays markets as rows with text "Over 2.5" and an adjacent odds element
    "generic_simple": {
        "market_selector": None,   # not used in text-scan fallback
        "text_scan": True,
    },
    # If you know a CSS selector for market rows, set it here:
    # "example_bookie": { "market_selector": "div.market-row", "selection_selector": ".sel", "odds_selector": ".odds" }
}

# Regex to find Over/Under lines like "Over 2.5", "Under 9.5" (case-insensitive)
OU_RE = re.compile(r"\b(Over|Under)\s*([0-9]+(?:\.[05])?)\b", flags=re.IGNORECASE)
# Regex to capture decimal odds (e.g., 1.95, 2.10)
ODDS_RE = re.compile(r"([0-9]{1,2}\.[0-9]{2})")

@utils.retry(exceptions=(requests.RequestException, Exception), tries=3, delay=1.0, backoff=2.0)
def fetch_url(url: str, timeout: int = 15) -> str:
    logger.info("Fetching URL: %s", url)
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "data_harvester/0.1 (+https://example.org)"})
    resp.raise_for_status()
    return resp.text

def find_ou_markets_text_scan(html: str) -> List[Dict]:
    """
    Heuristic text-scan: find occurrences like "Over 2.5" and try to find nearest odds number.
    Returns list of dicts: { 'selection': 'Over', 'line': 2.5, 'odds': 1.95 }
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    results = []
    for m in OU_RE.finditer(text):
        sel = m.group(1).capitalize()
        line = float(m.group(2))
        # search for an odds-looking number near the match span
        span_start, span_end = m.span()
        # window of characters after the match to find odds
        window = text[span_end: span_end + 80]
        odd_match = ODDS_RE.search(window)
        if odd_match:
            odds = float(odd_match.group(1))
            results.append({"selection": sel, "line": line, "odds": odds})
        else:
            # try look-behind
            window2 = text[max(0, span_start - 80): span_start]
            odd_match2 = ODDS_RE.search(window2)
            if odd_match2:
                odds = float(odd_match2.group(1))
                results.append({"selection": sel, "line": line, "odds": odds})
            else:
                # no odds found near this occurrence
                continue
    return results

def parse_and_insert(match_id: str, bookmaker: str, html: str, site_key: str = "generic_simple") -> int:
    """
    Parse the page and insert any found market odds into DB.
    Returns number of inserted rows.
    """
    inserted = 0
    cfg = SITE_CONFIGS.get(site_key, {})
    # Strategy 1: CSS selector-based parsing (if configured)
    if cfg.get("market_selector"):
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select(cfg["market_selector"])
        for r in rows:
            try:
                sel_text = r.select_one(cfg["selection_selector"]).get_text(strip=True)
                odds_text = r.select_one(cfg["odds_selector"]).get_text(strip=True)
                # Attempt to parse selection and line from sel_text, e.g., "Over 2.5"
                m = OU_RE.search(sel_text)
                if m:
                    selection = m.group(1).capitalize()
                    line = float(m.group(2))
                    odd_m = ODDS_RE.search(odds_text)
                    if odd_m:
                        odds = float(odd_m.group(1))
                        db.insert_market_odds(match_id, bookmaker, "over_under", selection, odds, line)
                        inserted += 1
            except Exception as exc:
                logger.exception("Failed to parse market row: %s", exc)

    # Strategy 2: Text-scan fallback (generic)
    if cfg.get("text_scan", False) or not cfg.get("market_selector"):
        try:
            ou_list = find_ou_markets_text_scan(html)
            for item in ou_list:
                db.insert_market_odds(match_id, bookmaker, "over_under", item["selection"], float(item["odds"]), float(item["line"]))
                inserted += 1
        except Exception as exc:
            logger.exception("Text-scan OU parsing failed: %s", exc)

    # Future: add corners/cards parsing heuristics (similar approach but using different regex or selectors)
    # Simple heuristic for corners/cards: look for "Corners" or "Cards" near a "Over X.Y" pattern
    # This is left as an exercise to adapt to a target site's DOM.

    return inserted

def run_job(match_id: str, bookmaker: str, url: str, site_key: str = "generic_simple") -> None:
    try:
        html = fetch_url(url)
    except Exception as exc:
        logger.exception("Failed fetching %s: %s", url, exc)
        return

    n = parse_and_insert(match_id, bookmaker, html, site_key=site_key)
    logger.info("Inserted %d market(s) for match %s from %s", n, match_id, bookmaker)

def main():
    p = argparse.ArgumentParser(description="Example bookmaker scraper that inserts odds_markets rows")
    p.add_argument("--match-id", help="Local match_id to associate odds with (required for single-run)", default=None)
    p.add_argument("--bookie", help="Bookmaker name", default="ExampleBookie")
    p.add_argument("--url", help="Match page URL to scrape", default=None)
    p.add_argument("--batch", help="JSON file with list of {match_id,bookie,url}", default=None)
    p.add_argument("--site-key", help="Site config key (default: generic_simple)", default="generic_simple")
    args = p.parse_args()

    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            jobs = json.load(f)
        for job in jobs:
            mid = job.get("match_id")
            bookie = job.get("bookie") or args.bookie
            url = job.get("url")
            if not mid or not url:
                logger.warning("Skipping invalid job: %s", job)
                continue
            run_job(mid, bookie, url, site_key=args.site_key)
    else:
        if not args.match_id or not args.url:
            print("For single-run, --match-id and --url are required")
            return
        run_job(args.match_id, args.bookie, args.url, site_key=args.site_key)

if __name__ == "__main__":
    main()
