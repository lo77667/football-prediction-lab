"""Adapter for Wikipedia / Wikidata metadata extraction (team names, players)."""

from typing import Any

import aiohttp

from .base import DataSource
from .cache import get_cache, init_cache, set_cache


class WikiDataAdapter(DataSource):
    def __init__(self):
        super().__init__(name="wikidata")
        init_cache()

    async def query_team_info(self, team_wikidata_id: str) -> dict[str, Any]:
        key = f"wikidata:{team_wikidata_id}"
        cached = get_cache(key, max_age_seconds=86400)
        if cached is not None:
            return cached
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{team_wikidata_id}.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                data = await resp.json()
        set_cache(key, self.name, url, data)
        return data
