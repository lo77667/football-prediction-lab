"""Optional API-Football adapter for fixtures, injuries, and lineups."""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from .base import DataSource, rate_limited
from .cache import get_cache, init_cache, set_cache


class ApiFootball(DataSource):
    """Fetch API-Sports football data without exposing the API key in logs."""

    base_url = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(name="api-football")
        init_cache()
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY")
        self._fetch = rate_limited(5, 60)(self._fetch_impl)

    async def _fetch_impl(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.api_key:
            raise PermissionError("API_FOOTBALL_KEY is required for API-Football")
        params = params or {}
        query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
        cache_key = f"api-football:{endpoint}?{query}"
        cached = get_cache(cache_key, max_age_seconds=300)
        if cached is not None:
            return cached
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"x-apisports-key": self.api_key}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status in {401, 403}:
                    raise PermissionError("API-Football key is unauthorized")
                if response.status == 429:
                    raise RuntimeError("API-Football rate limit exceeded")
                response.raise_for_status()
                payload = await response.json()
        set_cache(cache_key, self.name, url, payload)
        return payload

    async def fetch_fixtures(self, *, league: int, season: int) -> dict[str, Any]:
        return await self._fetch("fixtures", {"league": league, "season": season})

    async def fetch_injuries(self, *, fixture: int) -> dict[str, Any]:
        return await self._fetch("injuries", {"fixture": fixture})

    async def fetch_lineups(self, *, fixture: int) -> dict[str, Any]:
        return await self._fetch("fixtures/lineups", {"fixture": fixture})


__all__ = ["ApiFootball"]
