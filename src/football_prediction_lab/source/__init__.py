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
    "ShadowIngestResult",
    "QuarantineRow",
    "SourceBatch",
    "SourceRow",
]
