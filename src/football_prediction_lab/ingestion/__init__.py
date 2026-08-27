"""Deterministic, source-backed ingestion contracts and adapters."""

from football_prediction_lab.ingestion.adapter import DataSourceAdapter
from football_prediction_lab.ingestion.adapter import (
    UnavailableExternalAdapter as LocalUnavailableExternalAdapter,
)
from football_prediction_lab.ingestion.contracts import IngestionRun, MatchRecord, SourceRecord
from football_prediction_lab.ingestion.external_adapters import (
    ExternalSourceAdapter,
    UnavailableExternalAdapter,
)
from football_prediction_lab.ingestion.external_contracts import (
    ExternalSnapshotRecord,
    ExternalSource,
)
from football_prediction_lab.ingestion.local_csv import (
    IngestionResult,
    LocalCsvAdapter,
    ingest_file,
    replay_manifest,
    validate_manifest,
)
from football_prediction_lab.ingestion.odds_adapter import OddsAdapterResult, adapt_odds_payload

__all__ = [
    "DataSourceAdapter",
    "ExternalSnapshotRecord",
    "OddsAdapterResult",
    "ExternalSource",
    "ExternalSourceAdapter",
    "IngestionResult",
    "IngestionRun",
    "LocalCsvAdapter",
    "MatchRecord",
    "SourceRecord",
    "LocalUnavailableExternalAdapter",
    "UnavailableExternalAdapter",
    "adapt_odds_payload",
    "ingest_file",
    "replay_manifest",
    "validate_manifest",
]
