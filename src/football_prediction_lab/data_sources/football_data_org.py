"""Adapter for football-data.org v4 with caching and an explicit rate limit."""

import os
from typing import Any

import aiohttp

from .base import DataSource, rate_limited
from .cache import get_cache, init_cache, set_cache


class FootballDataOrg(DataSource):
    def __init__(self, token: str = None):
        super().__init__(name="football-data.org")
        init_cache()
        self.token = token or os.getenv("FOOTBALL_DATA_API_TOKEN")
        # 10 requests per minute -> rate_limited decorator with calls=10, period=60
        self._fetch = rate_limited(10, 60)(self._fetch_impl)

    async def _fetch_impl(self, endpoint: str) -> dict[str, Any]:
        url = f"https://api.football-data.org/v4/{endpoint.lstrip('/')}"
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
                    raise RuntimeError("football-data.org rate limit exceeded")
                if resp.status in {401, 403}:
                    raise PermissionError("football-data.org token is missing or unauthorized")
                resp.raise_for_status()
                data = await resp.json()
        set_cache(key, self.name, url, data)
        return data

    async def fetch_competition(self, comp_id: str) -> dict[str, Any]:
        return await self._fetch(f"competitions/{comp_id}/matches")
