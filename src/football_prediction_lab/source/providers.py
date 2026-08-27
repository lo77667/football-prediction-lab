"""Read-only football provider adapters with explicit network opt-in."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Base error for provider adapters."""


class ProviderNetworkDisabled(ProviderError):
    """Raised when a real network request is not explicitly enabled."""


class ProviderAuthenticationRequired(ProviderError):
    """Raised when a provider requires a credential that was not supplied."""


class ProviderPayloadError(ProviderError):
    """Raised when a provider response does not satisfy its adapter contract."""


@dataclass(frozen=True)
class ProviderMatch:
    provider: str
    external_id: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    status: str
    home_score: int | None = None
    away_score: int | None = None


@dataclass(frozen=True)
class ProviderBatch:
    provider: str
    endpoint: str
    response_sha256: str
    observed_at_utc: datetime
    matches: tuple[ProviderMatch, ...]


Transport = Callable[[str, Mapping[str, str], float], bytes]


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ProviderPayloadError("timestamp must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProviderPayloadError("timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ProviderPayloadError("timestamp must be explicit UTC")
    return parsed.astimezone(UTC)


def _score(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderPayloadError("score must be an integer or null")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() in {"", "-", "null", "None"}:
        return None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ProviderPayloadError("score must be an integer or null")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderPayloadError(f"{field} must be a non-empty string")
    return value.strip()


def _date(value: date | str) -> str:
    if isinstance(value, datetime):
        raise ValueError("fixture_date must be a date, not datetime")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise ValueError("fixture_date must be YYYY-MM-DD") from error
    raise TypeError("fixture_date must be a date or YYYY-MM-DD string")


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> bytes:
    request = Request(url, headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ProviderError(f"provider request failed: {type(error).__name__}") from error


class _ProviderClient:
    provider = "provider"
    base_url = ""
    token_header: str | None = None
    token_required = False

    def __init__(
        self,
        *,
        token: str | None = None,
        allow_network: bool = False,
        timeout_seconds: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.token = token.strip() if isinstance(token, str) and token.strip() else None
        self.allow_network = allow_network
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _default_transport

    def _request(self, path: str, params: Mapping[str, str]) -> tuple[str, bytes]:
        if self.token_required and not self.token:
            raise ProviderAuthenticationRequired(f"{self.provider} requires a token")
        query = urlencode(sorted(params.items()))
        endpoint = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            endpoint = f"{endpoint}?{query}"
        if not self.allow_network and self._transport is _default_transport:
            raise ProviderNetworkDisabled(
                f"{self.provider} network access is disabled; pass allow_network=True"
            )
        headers = {
            "Accept": "application/json",
            "User-Agent": "football-prediction-lab/1",
        }
        if self.token and self.token_header:
            headers[self.token_header] = self.token
        payload = self._transport(endpoint, headers, self.timeout_seconds)
        if not isinstance(payload, bytes):
            raise ProviderPayloadError("transport must return bytes")
        return endpoint, payload

    def _decode(self, endpoint: str, payload: bytes) -> tuple[object, str, datetime]:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProviderPayloadError(f"{self.provider} response is not valid JSON") from error
        return decoded, endpoint, datetime.now(UTC)


class SportScoreClient(_ProviderClient):
    """SportScore REST v1 adapter; anonymous access remains opt-in locally."""

    provider = "SportScore"
    base_url = "https://sportscore.com"

    def fetch_fixtures(
        self, fixture_date: date | str, *, competition: str | None = None
    ) -> ProviderBatch:
        params = {"date": _date(fixture_date), "sport": "football"}
        if competition is not None:
            params["competition"] = _text(competition, "competition")
        endpoint, payload = self._request("/api/v1/fixtures/", params)
        decoded, endpoint, observed = self._decode(endpoint, payload)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("matches"), list):
            raise ProviderPayloadError("SportScore response must contain matches list")
        matches = []
        for item in decoded["matches"]:
            if not isinstance(item, dict):
                raise ProviderPayloadError("SportScore match must be an object")
            matches.append(
                ProviderMatch(
                    provider=self.provider,
                    external_id=_text(item.get("slug") or item.get("url"), "slug/url"),
                    kickoff_utc=_utc(item.get("time")),
                    home_team=_text(item.get("home"), "home"),
                    away_team=_text(item.get("away"), "away"),
                    status=_text(item.get("status"), "status"),
                    home_score=_score(item.get("home_score")),
                    away_score=_score(item.get("away_score")),
                )
            )
        matches.sort(key=lambda item: (item.kickoff_utc, item.external_id))
        return ProviderBatch(
            self.provider,
            endpoint,
            hashlib.sha256(payload).hexdigest(),
            observed,
            tuple(matches),
        )


class FootballDataClient(_ProviderClient):
    """football-data.org v4 adapter using X-Auth-Token when supplied."""

    provider = "football-data.org"
    base_url = "https://api.football-data.org/v4"
    token_header = "X-Auth-Token"
    token_required = True

    def fetch_fixtures(
        self, fixture_date: date | str, *, competition: str | None = None
    ) -> ProviderBatch:
        day = _date(fixture_date)
        params = {"dateFrom": day, "dateTo": day}
        if competition is not None:
            params["competitions"] = _text(competition, "competition")
        endpoint, payload = self._request("/matches", params)
        decoded, endpoint, observed = self._decode(endpoint, payload)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("matches"), list):
            raise ProviderPayloadError("football-data.org response must contain matches list")
        matches = []
        for item in decoded["matches"]:
            if not isinstance(item, dict):
                raise ProviderPayloadError("football-data.org match must be an object")
            score = item.get("score") or {}
            full_time = score.get("fullTime") if isinstance(score, dict) else {}
            if not isinstance(full_time, dict):
                raise ProviderPayloadError("football-data.org fullTime must be an object")
            home_team = item.get("homeTeam") or {}
            away_team = item.get("awayTeam") or {}
            matches.append(
                ProviderMatch(
                    provider=self.provider,
                    external_id=str(item.get("id")),
                    kickoff_utc=_utc(item.get("utcDate")),
                    home_team=_text(home_team.get("name"), "homeTeam.name"),
                    away_team=_text(away_team.get("name"), "awayTeam.name"),
                    status=_text(item.get("status"), "status"),
                    home_score=_score(full_time.get("home")),
                    away_score=_score(full_time.get("away")),
                )
            )
        matches.sort(key=lambda item: (item.kickoff_utc, item.external_id))
        return ProviderBatch(
            self.provider,
            endpoint,
            hashlib.sha256(payload).hexdigest(),
            observed,
            tuple(matches),
        )


class TheSportsDBClient(_ProviderClient):
    """TheSportsDB v1 adapter; the API key is never embedded in source."""

    provider = "TheSportsDB"
    base_url = "https://www.thesportsdb.com"
    token_required = True

    def fetch_fixtures(self, fixture_date: date | str) -> ProviderBatch:
        day = _date(fixture_date)
        endpoint_path = f"/api/v1/json/{self.token}/eventsday.php"
        endpoint, payload = self._request(endpoint_path, {"d": day, "s": "Soccer"})
        safe_endpoint = endpoint.replace(self.token or "", "<redacted>")
        decoded, _, observed = self._decode(endpoint, payload)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("events"), list):
            raise ProviderPayloadError("TheSportsDB response must contain events list")
        matches = []
        for item in decoded["events"]:
            if not isinstance(item, dict):
                raise ProviderPayloadError("TheSportsDB event must be an object")
            timestamp = item.get("strTimestamp") or item.get("dateEvent")
            if isinstance(timestamp, str) and len(timestamp) == 10:
                timestamp = f"{timestamp}T00:00:00+00:00"
            matches.append(
                ProviderMatch(
                    provider=self.provider,
                    external_id=_text(str(item.get("idEvent")), "idEvent"),
                    kickoff_utc=_utc(timestamp),
                    home_team=_text(item.get("strHomeTeam"), "strHomeTeam"),
                    away_team=_text(item.get("strAwayTeam"), "strAwayTeam"),
                    status=_text(item.get("strStatus") or "scheduled", "strStatus"),
                    home_score=_score(item.get("intHomeScore")),
                    away_score=_score(item.get("intAwayScore")),
                )
            )
        matches.sort(key=lambda item: (item.kickoff_utc, item.external_id))
        return ProviderBatch(
            self.provider,
            safe_endpoint,
            hashlib.sha256(payload).hexdigest(),
            observed,
            tuple(matches),
        )


__all__ = [
    "FootballDataClient",
    "ProviderAuthenticationRequired",
    "ProviderBatch",
    "ProviderError",
    "ProviderMatch",
    "ProviderNetworkDisabled",
    "ProviderPayloadError",
    "SportScoreClient",
    "TheSportsDBClient",
]
