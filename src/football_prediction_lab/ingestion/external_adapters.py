"""External-source adapter contracts with a no-network deferred implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from football_prediction_lab.ingestion.external_contracts import ExternalSource


class ExternalSourceAdapter(ABC):
    """Lifecycle interface for an explicitly authorized external source."""

    @abstractmethod
    def discover_source(self) -> ExternalSource:
        """Return non-secret source metadata."""

    @abstractmethod
    def fetch_snapshot(self) -> pd.DataFrame:
        """Fetch a source snapshot; implementations must preserve raw meaning."""

    @abstractmethod
    def normalize_snapshot(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Normalize source observations without adding labels or post-match data."""

    @abstractmethod
    def validate_provenance(self, source: ExternalSource, frame: pd.DataFrame) -> None:
        """Validate source metadata and snapshot provenance."""

    @abstractmethod
    def validate_license(self, source: ExternalSource) -> None:
        """Validate license or usage-policy evidence."""

    @abstractmethod
    def match_to_event(self, frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
        """Deterministically link records to known events or return quarantine metadata."""

    @abstractmethod
    def write_immutable_snapshot(self, frame: pd.DataFrame, destination: Path) -> str:
        """Write exact authorized bytes once and return their SHA-256."""

    @abstractmethod
    def build_manifest(self, source: ExternalSource, **metadata: Any) -> dict[str, Any]:
        """Build a JSON-safe source manifest."""


class UnavailableExternalAdapter(ExternalSourceAdapter):
    """Explicit deferred adapter that never performs network access."""

    def __init__(self, reason: str = "no authorized external source is configured") -> None:
        self.reason = reason

    def _raise(self) -> None:
        raise RuntimeError(f"UnavailableExternalAdapter: {self.reason}")

    def discover_source(self) -> ExternalSource:
        self._raise()
        raise AssertionError("unreachable")

    def fetch_snapshot(self) -> pd.DataFrame:
        self._raise()
        raise AssertionError("unreachable")

    def normalize_snapshot(self, frame: pd.DataFrame) -> pd.DataFrame:
        self._raise()
        raise AssertionError("unreachable")

    def validate_provenance(self, source: ExternalSource, frame: pd.DataFrame) -> None:
        self._raise()

    def validate_license(self, source: ExternalSource) -> None:
        self._raise()

    def match_to_event(self, frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
        self._raise()
        raise AssertionError("unreachable")

    def write_immutable_snapshot(self, frame: pd.DataFrame, destination: Path) -> str:
        self._raise()
        raise AssertionError("unreachable")

    def build_manifest(self, source: ExternalSource, **metadata: Any) -> dict[str, Any]:
        self._raise()
        raise AssertionError("unreachable")
