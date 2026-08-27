"""Local and authorized source adapters for Cycle 46."""

from .file_adapter import LocalJsonlSource, QuarantineRow, SourceBatch, SourceRow
from .openligadb import (
    OpenLigaBatch,
    OpenLigaDBClient,
    OpenLigaDBError,
    OpenLigaDBNetworkDisabled,
    OpenLigaDBPayloadError,
    OpenLigaMatch,
    OpenLigaTeam,
)
from .providers import (
    FootballDataClient,
    ProviderAuthenticationRequired,
    ProviderBatch,
    ProviderError,
    ProviderMatch,
    ProviderNetworkDisabled,
    ProviderPayloadError,
    SportScoreClient,
    TheSportsDBClient,
)
from .registry import DEFAULT_CONFIG, ProviderConfigError, build_enabled_clients
from .shadow_ingest import OpenLigaDBShadowIngestor, ShadowIngestResult

__all__ = [
    "LocalJsonlSource",
    "OpenLigaBatch",
    "OpenLigaDBClient",
    "OpenLigaDBError",
    "OpenLigaDBNetworkDisabled",
    "OpenLigaDBPayloadError",
    "OpenLigaMatch",
    "OpenLigaTeam",
    "OpenLigaDBShadowIngestor",
    "DEFAULT_CONFIG",
    "FootballDataClient",
    "ProviderAuthenticationRequired",
    "ProviderBatch",
    "ProviderConfigError",
    "ProviderError",
    "ProviderMatch",
    "ProviderNetworkDisabled",
    "ProviderPayloadError",
    "SportScoreClient",
    "TheSportsDBClient",
    "build_enabled_clients",
    "ShadowIngestResult",
    "QuarantineRow",
    "SourceBatch",
    "SourceRow",
]
