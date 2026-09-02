"""Adapter for football-data.co.uk CSV files (free historical odds and results)."""
import csv
import io
import asyncio
from typing import Dict, Any, List
from .base import DataSource
from .cache import init_cache, get_cache, set_cache

class FootballDataCoUK(DataSource):
    def __init__(self):
        super().__init__(name="football-data.co.uk")
        init_cache()

    async def fetch_csv_from_url(self, url: str, cache_ttl: int = 86400) -> List[Dict[str, Any]]:
        key = f"fdco:{url}"
        cached = get_cache(key, max_age_seconds=cache_ttl)
        if cached is not None:
            return cached
        # use aiohttp to fetch
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                text = await resp.text()
        reader = csv.DictReader(io.StringIO(text))
        rows = [r for r in reader]
        set_cache(key, self.name, url, rows)
        return rows

    async def list_seasons_csv(self, base_url: str) -> List[str]:
        # base_url example: https://www.football-data.co.uk/mmz4281/2223/E0.csv
        # For simplicity caller provides URLs or we can list a small hardcoded set
        return [base_url]
