"""Adapter for football-data.org free tier with explicit rate limit (10 req/min).
Requires env var FOOTBALL_DATA_ORG_TOKEN (free signup, no card required for free tier).
"""
import os
import aiohttp
import asyncio
from typing import Any, Dict
from .base import DataSource, rate_limited
from .cache import init_cache, get_cache, set_cache

class FootballDataOrg(DataSource):
    def __init__(self, token: str = None):
        super().__init__(name="football-data.org")
        init_cache()
        self.token = token or os.getenv("FOOTBALL_DATA_ORG_TOKEN")
        # 10 requests per minute -> rate_limited decorator with calls=10, period=60
        self._fetch = rate_limited(10, 60)(self._fetch_impl)

    async def _fetch_impl(self, endpoint: str) -> Dict[str, Any]:
        url = f"https://api.football-data.org/v2/{endpoint}"
        key = f"fdo:{endpoint}"
        cached = get_cache(key, max_age_seconds=60)
        if cached is not None:
            return cached
        headers = {}
        if self.token:
            headers["X-Auth-Token"] = self.token
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 429:
                    # hit rate limit
                    raise Exception("football-data.org rate limit exceeded")
                data = await resp.json()
        set_cache(key, self.name, url, data)
        return data

    async def fetch_competition(self, comp_id: str) -> Dict[str, Any]:
        return await self._fetch(f"competitions/{comp_id}/matches")
