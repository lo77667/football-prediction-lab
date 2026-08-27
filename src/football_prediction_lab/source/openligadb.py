"""OpenLigaDB source adapter with explicit network opt-in."""

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


class OpenLigaDBError(RuntimeError):
    """Base error for the OpenLigaDB adapter."""


class OpenLigaDBNetworkDisabled(OpenLigaDBError):
    """Raised when a network call is attempted without explicit opt-in."""


class OpenLigaDBPayloadError(OpenLigaDBError):
    """Raised when the provider payload does not satisfy the expected contract."""


@dataclass(frozen=True)
class OpenLigaTeam:
    team_id: int
    name: str


@dataclass(frozen=True)
class OpenLigaMatch:
    match_id: int
    kickoff_utc: datetime
    league_id: int | None
    league_name: str
    league_shortcut: str
    league_season: int
    team1: OpenLigaTeam
    team2: OpenLigaTeam
    finished: bool
    results: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class OpenLigaBatch:
    matches: tuple[OpenLigaMatch, ...]
    endpoint: str
    response_sha256: str
    fetched_at_utc: datetime
    from_cache: bool


Transport = Callable[[str, float], bytes]


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OpenLigaDBPayloadError("timestamp must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise OpenLigaDBPayloadError("timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise OpenLigaDBPayloadError("timestamp must be explicit UTC")
    return parsed.astimezone(UTC)


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenLigaDBPayloadError(f"{field} must be an integer")
    return value


def _team(value: Any, field: str) -> OpenLigaTeam:
    if not isinstance(value, dict):
        raise OpenLigaDBPayloadError(f"{field} must be an object")
    allowed = {"teamId", "teamName", "shortName", "teamIconUrl", "teamGroupName"}
    if not set(value).issubset(allowed) or "teamId" not in value or "teamName" not in value:
        raise OpenLigaDBPayloadError(f"{field} has invalid fields")
    team_id = _required_int(value["teamId"], f"{field}.teamId")
    name = value["teamName"]
    if not isinstance(name, str) or not name.strip():
        raise OpenLigaDBPayloadError(f"{field}.teamName must be non-empty")
    return OpenLigaTeam(team_id, name.strip())


def _match(value: Any, *, shortcut: str, season: int) -> OpenLigaMatch:
    if not isinstance(value, dict):
        raise OpenLigaDBPayloadError("match must be an object")
    required = {
        "matchID",
        "matchDateTimeUTC",
        "team1",
        "team2",
        "matchIsFinished",
        "matchResults",
    }
    if not required.issubset(value):
        raise OpenLigaDBPayloadError("match is missing required fields")
    allowed = required | {
        "goals",
        "group",
        "lastUpdateDateTime",
        "leagueId",
        "leagueName",
        "leagueSeason",
        "leagueShortcut",
        "location",
        "matchDateTime",
        "numberOfViewers",
        "timeZoneID",
    }
    if not set(value).issubset(allowed):
        raise OpenLigaDBPayloadError("match has unexpected fields")
    results = value["matchResults"]
    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        raise OpenLigaDBPayloadError("matchResults must be a list of objects")
    match_id = _required_int(value["matchID"], "matchID")
    league_id = value.get("leagueId")
    if league_id is not None:
        league_id = _required_int(league_id, "leagueId")
    league_name = value.get("leagueName", "")
    if not isinstance(league_name, str):
        raise OpenLigaDBPayloadError("leagueName must be a string")
    provider_shortcut = value.get("leagueShortcut", shortcut)
    if provider_shortcut != shortcut:
        raise OpenLigaDBPayloadError("league shortcut mismatch")
    provider_season = value.get("leagueSeason", season)
    if provider_season != season:
        raise OpenLigaDBPayloadError("league season mismatch")
    if not isinstance(value["matchIsFinished"], bool):
        raise OpenLigaDBPayloadError("matchIsFinished must be boolean")
    return OpenLigaMatch(
        match_id=match_id,
        kickoff_utc=_utc(value["matchDateTimeUTC"]),
        league_id=league_id,
        league_name=league_name,
        league_shortcut=shortcut,
        league_season=season,
        team1=_team(value["team1"], "team1"),
        team2=_team(value["team2"], "team2"),
        finished=value["matchIsFinished"],
        results=tuple(dict(item) for item in results),
    )


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "football-prediction-lab/1"},
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise OpenLigaDBError(f"OpenLigaDB request failed: {type(error).__name__}") from error


class OpenLigaDBClient:
    """Read OpenLigaDB data with no network access unless explicitly enabled."""

    base_url = "https://api.openligadb.de"

    def __init__(
        self,
        *,
        allow_network: bool = False,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 1.0,
        cache_ttl_seconds: float | None = None,
        transport: Transport | None = None,
    ) -> None:
        if timeout_seconds <= 0 or min_interval_seconds < 0:
            raise ValueError("timeout and rate interval must be non-negative, timeout positive")
        if cache_ttl_seconds is not None and cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds must be non-negative or None")
        self.allow_network = allow_network
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._transport = transport or _default_transport
        self._cache: dict[str, tuple[bytes, datetime]] = {}
        self._last_request = 0.0
        self._lock = Lock()

    def _request(self, endpoint: str) -> tuple[bytes, bool]:
        with self._lock:
            cached = self._cache.get(endpoint)
            if cached is not None:
                cached_payload, cached_at = cached
                cache_fresh = (
                    self.cache_ttl_seconds is None
                    or (datetime.now(UTC) - cached_at).total_seconds() < self.cache_ttl_seconds
                )
                if cache_fresh:
                    return cached_payload, True
                self._cache.pop(endpoint, None)
            if not self.allow_network and self._transport is _default_transport:
                raise OpenLigaDBNetworkDisabled(
                    "OpenLigaDB network access is disabled; pass allow_network=True"
                )
            wait = self.min_interval_seconds - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            payload = self._transport(endpoint, self.timeout_seconds)
            self._last_request = time.monotonic()
            if not isinstance(payload, bytes):
                raise OpenLigaDBPayloadError("transport must return bytes")
            self._cache[endpoint] = (payload, datetime.now(UTC))
            return payload, False

    def fetch_league_season(self, league_shortcut: str, season: int) -> OpenLigaBatch:
        if not isinstance(league_shortcut, str) or not league_shortcut.isalnum():
            raise ValueError("league_shortcut must be alphanumeric")
        if isinstance(season, bool) or not isinstance(season, int) or not 1900 <= season <= 2200:
            raise ValueError("season must be a valid year")
        endpoint = f"{self.base_url}/getmatchdata/{league_shortcut}/{season}"
        payload, from_cache = self._request(endpoint)
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise OpenLigaDBPayloadError("response is not valid JSON") from error
        if not isinstance(decoded, list):
            raise OpenLigaDBPayloadError("response must be a list")
        matches = tuple(
            sorted(
                (_match(item, shortcut=league_shortcut, season=season) for item in decoded),
                key=lambda item: (item.kickoff_utc, item.match_id),
            )
        )
        return OpenLigaBatch(
            matches=matches,
            endpoint=endpoint,
            response_sha256=hashlib.sha256(payload).hexdigest(),
            fetched_at_utc=datetime.now(UTC),
            from_cache=from_cache,
        )
