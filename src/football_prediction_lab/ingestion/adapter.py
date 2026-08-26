"""Interfaces for deterministic, source-backed ingestion adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class DataSourceAdapter(ABC):
    """Lifecycle contract for a source adapter."""

    @abstractmethod
    def discover(self) -> dict[str, Any]:
        """Return non-secret source metadata."""

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Read source rows without changing their meaning."""

    @abstractmethod
    def normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Map source columns into the canonical pre-match schema."""

    @abstractmethod
    def validate(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Return accepted rows and bounded quarantine records."""

    @abstractmethod
    def write_immutable_raw(self, destination: Path) -> str:
        """Write the exact source bytes once and return its SHA-256."""

    @abstractmethod
    def build_manifest(self, **metadata: Any) -> dict[str, Any]:
        """Build a JSON-safe provenance manifest."""


class UnavailableExternalAdapter(DataSourceAdapter):
    """Explicit fail-closed placeholder for unconfigured external sources."""

    def __init__(self, reason: str = "external source is not configured") -> None:
        self.reason = reason

    def _raise(self) -> None:
        raise RuntimeError(f"UnavailableExternalAdapter: {self.reason}")

    def discover(self) -> dict[str, Any]:
        self._raise()
        return {}

    def fetch(self) -> pd.DataFrame:
        self._raise()
        return pd.DataFrame()

    def normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        self._raise()
        return frame

    def validate(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        self._raise()
        return frame, []

    def write_immutable_raw(self, destination: Path) -> str:
        self._raise()
        return ""

    def build_manifest(self, **metadata: Any) -> dict[str, Any]:
        self._raise()
        return metadata
