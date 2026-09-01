"""Read-only client for the FreePublicAPIs discovery catalog.

This module discovers candidate providers; it is not a football data source
and must not be treated as evidence that a listed endpoint is safe or free.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FreePublicAPIsError(RuntimeError):
    """Base catalog error."""


@dataclass(frozen=True)
class CatalogEntry:
    entry_id: int
    title: str
    description: str
    documentation: str | None
    source: str | None
    health: int | None
    raw: dict


@dataclass(frozen=True)
class CatalogResponse:
    endpoint: str
    entries: tuple[CatalogEntry, ...]
    response_sha256: str
    fetched_at_utc: datetime


Transport = Callable[[str, float], bytes]


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": "football-prediction-lab/1"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise FreePublicAPIsError(
            f"FreePublicAPIs request failed: {type(error).__name__}"
        ) from error


def _entry(value: object) -> CatalogEntry:
    if not isinstance(value, dict):
        raise FreePublicAPIsError("catalog entry must be an object")
    if isinstance(value.get("id"), bool) or not isinstance(value.get("id"), int):
        raise FreePublicAPIsError("catalog entry id must be an integer")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise FreePublicAPIsError("catalog entry title must be non-empty")
    health = value.get("health")
    if health is not None and (isinstance(health, bool) or not isinstance(health, int)):
        raise FreePublicAPIsError("catalog health must be an integer")
    return CatalogEntry(
        value["id"],
        value["title"].strip(),
        value.get("description", "") if isinstance(value.get("description", ""), str) else "",
        value.get("documentation") if isinstance(value.get("documentation"), str) else None,
        value.get("source") if isinstance(value.get("source"), str) else None,
        health,
        dict(value),
    )


class FreePublicAPIsCatalogClient:
    """Fetch and locally search the public discovery catalog."""

    base_url = "https://www.freepublicapis.com/api/apis"

    def __init__(
        self, *, timeout_seconds: float = 15.0, transport: Transport | None = None
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _default_transport

    def fetch(self, *, limit: int = 1000, sort: str = "all") -> CatalogResponse:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if not isinstance(sort, str) or not sort.strip():
            raise ValueError("sort must be non-empty")
        endpoint = f"{self.base_url}?{urlencode({'limit': limit, 'sort': sort})}"
        payload = self._transport(endpoint, self.timeout_seconds)
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise FreePublicAPIsError("catalog response is not valid JSON") from error
        if not isinstance(decoded, list):
            raise FreePublicAPIsError("catalog response must be a JSON list")
        return CatalogResponse(
            endpoint,
            tuple(_entry(item) for item in decoded),
            hashlib.sha256(payload).hexdigest(),
            datetime.now(UTC),
        )

    @staticmethod
    def search(response: CatalogResponse, phrase: str) -> tuple[CatalogEntry, ...]:
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError("phrase must be non-empty")
        needle = phrase.casefold()
        return tuple(
            entry
            for entry in response.entries
            if needle in f"{entry.title} {entry.description}".casefold()
        )


__all__ = ["CatalogEntry", "CatalogResponse", "FreePublicAPIsCatalogClient", "FreePublicAPIsError"]
