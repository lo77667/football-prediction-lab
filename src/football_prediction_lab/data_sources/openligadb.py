"""Adapter for OpenLigaDB (free)."""
import aiohttp
import asyncio
from typing import Any, Dict
from .base import DataSource
from .cache import init_cache, get_cache, set_cache

class OpenLigaDB(DataSource):
    def __init__(self):
        super().__init__(name="OpenLigaDB")
        init_cache()

    async def fetch_matches_for_league(self, league_shortcut: str) -> Dict[str, Any]:
        url = f"https://www.openligadb.de/api/getmatchdata/{league_shortcut}"  # example endpoint
        key = f"openligadb:{league_shortcut}"
        cached = get_cache(key, max_age_seconds=300)
        if cached is not None:
            return cached
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                data = await resp.json()
        set_cache(key, self.name, url, data)
        return data
