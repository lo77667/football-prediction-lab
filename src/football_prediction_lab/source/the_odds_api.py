"""Authenticated read-only client for The Odds API."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OddsApiError(RuntimeError):
    """Base odds provider error."""


class OddsApiAuthenticationError(OddsApiError):
    """Raised when the API key is missing or rejected."""


class OddsApiPayloadError(OddsApiError):
    """Raised when the response does not satisfy the basic odds contract."""


@dataclass(frozen=True)
class OddsResponse:
    endpoint: str
    payload: list[dict]
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
    except HTTPError as error:
        if error.code in {401, 403}:
            raise OddsApiAuthenticationError(
                f"The Odds API rejected credentials: HTTP {error.code}"
            ) from error
        raise OddsApiError(f"The Odds API request failed: HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise OddsApiError(f"The Odds API request failed: {type(error).__name__}") from error


class TheOddsApiClient:
    """Read odds snapshots. No write, order, or betting endpoint is exposed."""

    base_url = "https://api.the-odds-api.com/v4"

    def __init__(
        self, api_key: str, *, timeout_seconds: float = 15.0, transport: Transport | None = None
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _default_transport

    def fetch_odds(
        self,
        sport: str,
        *,
        regions: str = "eu",
        markets: str = "h2h",
        odds_format: str = "decimal",
        date_format: str = "iso",
    ) -> OddsResponse:
        values = {
            "sport": sport,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError(
                "sport, regions, markets, odds_format, and date_format must be non-empty strings"
            )
        query = urlencode(
            {
                "apiKey": self.api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
                "dateFormat": date_format,
            }
        )
        endpoint = f"{self.base_url}/sports/{sport.strip()}/odds?{query}"
        payload_bytes = self._transport(endpoint, self.timeout_seconds)
        try:
            payload = json.loads(payload_bytes)
        except (TypeError, json.JSONDecodeError) as error:
            raise OddsApiPayloadError("response is not valid JSON") from error
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise OddsApiPayloadError("response must be a JSON list of event objects")
        return OddsResponse(
            endpoint, payload, hashlib.sha256(payload_bytes).hexdigest(), datetime.now(UTC)
        )


__all__ = [
    "OddsApiAuthenticationError",
    "OddsApiError",
    "OddsApiPayloadError",
    "OddsResponse",
    "TheOddsApiClient",
]
