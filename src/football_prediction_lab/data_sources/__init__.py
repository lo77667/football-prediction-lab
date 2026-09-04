"""Data sources package for football_prediction_lab
Adapters for free data sources with caching, rate-limiting and retry.
"""

from .base import DataSource, RateLimitExceeded
from .cache import Cache
from .football_data_co_uk import FootballDataCoUK
from .football_data_org import FootballDataOrg
from .openligadb import OpenLigaDB
from .wikidata import WikiDataAdapter

__all__ = [
    "DataSource",
    "RateLimitExceeded",
    "Cache",
    "FootballDataCoUK",
    "OpenLigaDB",
    "FootballDataOrg",
    "WikiDataAdapter",
]
