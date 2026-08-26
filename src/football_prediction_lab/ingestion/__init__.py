"""Deterministic, source-backed ingestion contracts and adapters."""

from football_prediction_lab.ingestion.adapter import DataSourceAdapter, UnavailableExternalAdapter
from football_prediction_lab.ingestion.contracts import IngestionRun, MatchRecord, SourceRecord
from football_prediction_lab.ingestion.local_csv import (
    IngestionResult,
    LocalCsvAdapter,
    ingest_file,
    replay_manifest,
    validate_manifest,
)

__all__ = [
    "DataSourceAdapter",
    "IngestionResult",
    "IngestionRun",
    "LocalCsvAdapter",
    "MatchRecord",
    "SourceRecord",
    "UnavailableExternalAdapter",
    "ingest_file",
    "replay_manifest",
    "validate_manifest",
]
