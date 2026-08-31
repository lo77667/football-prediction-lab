"""World Cup 2026 public fixture API adapter.

This adapter is intentionally limited to fixtures/schedule data. It does not
invent results, odds, events, or player metrics, and network access is opt-in.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WorldCup2026Error(RuntimeError):
    """Base adapter error."""


class WorldCup2026NetworkDisabled(WorldCup2026Error):
    """Raised when live access was not explicitly enabled."""


class WorldCup2026PayloadError(WorldCup2026Error):
    """Raised when the provider response violates the expected schema."""


@dataclass(frozen=True)
class WorldCupTeam:
    code: str
    name: str


@dataclass(frozen=True)
class WorldCupFixture:
    fixture_id: int
    stage: str
    stage_name: str
    group: str | None
    venue: str
    kickoff_utc: datetime
    home: WorldCupTeam
    away: WorldCupTeam
    attribution_url: str | None


@dataclass(frozen=True)
class WorldCupBatch:
    fixtures: tuple[WorldCupFixture, ...]
    endpoint: str
    response_sha256: str
    fetched_at_utc: datetime
    from_cache: bool
    provider_version: str


Transport = Callable[[str, float], bytes]


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise WorldCup2026PayloadError("kickoff.utc must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise WorldCup2026PayloadError("kickoff.utc is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise WorldCup2026PayloadError("kickoff.utc must be explicit UTC")
    return parsed.astimezone(UTC)


def _team(value: Any, field: str) -> WorldCupTeam:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("code"), str)
        or not isinstance(value.get("name"), str)
    ):
        raise WorldCup2026PayloadError(f"{field} must contain string code and name")
    code = value["code"].strip()
    name = value["name"].strip()
    if not code or not name:
        raise WorldCup2026PayloadError(f"{field} code and name must be non-empty")
    return WorldCupTeam(code=code, name=name)


def _fixture(value: Any) -> WorldCupFixture:
    if not isinstance(value, dict):
        raise WorldCup2026PayloadError("fixture must be an object")
    required = {"id", "stage", "stageName", "venue", "kickoff", "home", "away"}
    if not required.issubset(value):
        raise WorldCup2026PayloadError("fixture is missing required fields")
    if isinstance(value["id"], bool) or not isinstance(value["id"], int):
        raise WorldCup2026PayloadError("fixture id must be an integer")
    if (
        not isinstance(value["stage"], str)
        or not isinstance(value["stageName"], str)
        or not isinstance(value["venue"], str)
    ):
        raise WorldCup2026PayloadError("fixture stage and venue fields must be strings")
    kickoff = value["kickoff"]
    if not isinstance(kickoff, dict):
        raise WorldCup2026PayloadError("kickoff must be an object")
    attribution = value.get("attributionSnippets", {})
    attribution_url = None
    if isinstance(attribution, dict) and isinstance(attribution.get("text"), str):
        candidate = attribution["text"].rsplit(": ", 1)[-1]
        attribution_url = candidate if candidate.startswith("https://") else None
    return WorldCupFixture(
        fixture_id=value["id"],
        stage=value["stage"].strip(),
        stage_name=value["stageName"].strip(),
        group=value.get("group") if isinstance(value.get("group"), str) else None,
        venue=value["venue"].strip(),
        kickoff_utc=_utc(kickoff.get("utc")),
        home=_team(value["home"], "home"),
        away=_team(value["away"], "away"),
        attribution_url=attribution_url,
    )


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": "football-prediction-lab/1"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise WorldCup2026Error(f"World Cup API request failed: {type(error).__name__}") from error


class WorldCup2026Client:
    """Fetch World Cup 2026 fixtures with explicit network opt-in."""

    endpoint = "https://ay-worldcup2026.zeabur.app/api/public/v1/matches"

    def __init__(
        self,
        *,
        allow_network: bool = False,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 1.0,
        cache_ttl_seconds: float | None = None,
        transport: Transport | None = None,
    ) -> None:
        if (
            timeout_seconds <= 0
            or min_interval_seconds < 0
            or (cache_ttl_seconds is not None and cache_ttl_seconds < 0)
        ):
            raise ValueError("invalid timeout, interval, or cache TTL")
        self.allow_network = allow_network
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._transport = transport or _default_transport
        self._cache: tuple[bytes, datetime] | None = None
        self._last_request = 0.0
        self._lock = Lock()

    def fetch_fixtures(self, timezone: str = "UTC") -> WorldCupBatch:
        if not isinstance(timezone, str) or not timezone.strip():
            raise ValueError("timezone must be a non-empty string")
        endpoint = f"{self.endpoint}?timezone={timezone}"
        with self._lock:
            payload, from_cache = self._request(endpoint)
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise WorldCup2026PayloadError("response is not valid JSON") from error
        if (
            not isinstance(decoded, dict)
            or not isinstance(decoded.get("matches"), list)
            or not isinstance(decoded.get("version"), str)
        ):
            raise WorldCup2026PayloadError("response must contain version and matches")
        fixtures = tuple(
            sorted(
                (_fixture(item) for item in decoded["matches"]),
                key=lambda item: (item.kickoff_utc, item.fixture_id),
            )
        )
        declared_count = decoded.get("count")
        if declared_count != len(fixtures):
            raise WorldCup2026PayloadError("declared count does not match fixture count")
        return WorldCupBatch(
            fixtures,
            endpoint,
            hashlib.sha256(payload).hexdigest(),
            datetime.now(UTC),
            from_cache,
            decoded["version"],
        )

    def _request(self, endpoint: str) -> tuple[bytes, bool]:
        if self._cache is not None and self.cache_ttl_seconds is not None:
            payload, cached_at = self._cache
            if (datetime.now(UTC) - cached_at).total_seconds() < self.cache_ttl_seconds:
                return payload, True
            self._cache = None
        if not self.allow_network and self._transport is _default_transport:
            raise WorldCup2026NetworkDisabled(
                "World Cup API network access is disabled; pass allow_network=True"
            )
        wait = self.min_interval_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        payload = self._transport(endpoint, self.timeout_seconds)
        if not isinstance(payload, bytes):
            raise WorldCup2026PayloadError("transport must return bytes")
        self._last_request = time.monotonic()
        self._cache = (payload, datetime.now(UTC))
        return payload, False


__all__ = [
    "WorldCupBatch",
    "WorldCup2026Client",
    "WorldCup2026Error",
    "WorldCupFixture",
    "WorldCup2026NetworkDisabled",
    "WorldCup2026PayloadError",
    "WorldCupTeam",
]
