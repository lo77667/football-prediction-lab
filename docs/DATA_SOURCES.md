# DATA_SOURCES.md

This document lists the free data sources used by football-prediction-lab, their limits, coverage and notes.

1) football-data.co.uk
- Type: Historical CSV files (results, match stats, closing odds from multiple bookmakers)
- Access: Public CSV files; no API key required
- Rate limit: N/A (static files). Treat as unlimited for reads, but be polite when downloading large datasets.
- Coverage: Many European leagues; seasons by year in mmz4281 folder. Check site for exact list.
- Update frequency: Static historical seasons; new season CSVs uploaded seasonally.
- Notes: We cache fetched CSVs locally in SQLite to avoid repeated downloads.

2) OpenLigaDB
- Type: Free JSON API providing match data for supported leagues (Germany and others)
- Access: No API key required
- Rate limit: Not formally specified; we apply client-side caching (5 min) and a conservative 1 request per 1 second spacing.
- Coverage: Primarily German leagues; varies by league.
- Update frequency: Live during matchdays; use caching to avoid over-querying.

3) football-data.org (free tier)
- Type: REST API (matches, competitions, teams)
- Access: Requires free API token (no credit card required)
- Rate limit: Free tier 10 requests per minute (as of doc). We enforce 10 req/min client-side using a rate limiter.
- Coverage: Many international competitions and leagues, check the API docs
- Update frequency: Near real-time; respect rate limit and cache responses (default 60s cache)

4) Wikipedia / Wikidata
- Type: Metadata (team descriptions, player pages, IDs)
- Access: Public; no key required
- Rate limit: Be polite — we cache responses for 24 hours. Use Wikidata sparingly for metadata only (do not use for match results).
- Coverage: Global

Caching policy
- All adapters write responses to a shared SQLite cache (data_harvester.db table data_cache) to minimize repeated requests and protect free-tier limits.
- TTLs: Each adapter documents default TTLs (CSV long-term, API short-term like 60s). Adjust per use-case.

If you need additional free sources, ask for approval before adding them.
