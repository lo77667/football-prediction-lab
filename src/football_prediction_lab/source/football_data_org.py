"""Explicitly authenticated Football-Data.org client.

The client returns validated raw JSON and metadata. It does not silently
retry authentication failures or turn provider data into betting actions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FootballDataOrgError(RuntimeError):
    """Base provider error."""


class FootballDataOrgAuthenticationError(FootballDataOrgError):
    """Raised for missing or rejected credentials."""


class FootballDataOrgPayloadError(FootballDataOrgError):
    """Raised for malformed provider JSON."""


@dataclass(frozen=True)
class RawProviderResponse:
    endpoint: str
    payload: dict
    response_sha256: str
    fetched_at_utc: datetime


Transport = Callable[[str, dict[str, str], float], bytes]


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as error:
        if error.code in {401, 403}:
            raise FootballDataOrgAuthenticationError(
                f"Football-Data.org rejected credentials: HTTP {error.code}"
            ) from error
        raise FootballDataOrgError(
            f"Football-Data.org request failed: HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise FootballDataOrgError(
            f"Football-Data.org request failed: {type(error).__name__}"
        ) from error


class FootballDataOrgClient:
    """Fetch Football-Data.org resources with an explicit API token."""

    base_url = "https://api.football-data.org/v4"

    def __init__(
        self, api_token: str, *, timeout_seconds: float = 15.0, transport: Transport | None = None
    ) -> None:
        if not isinstance(api_token, str) or not api_token.strip():
            raise ValueError("api_token must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.api_token = api_token.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _default_transport

    def fetch_matches(
        self,
        competition: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> RawProviderResponse:
        if not isinstance(competition, str) or not competition.isalnum():
            raise ValueError("competition must be alphanumeric")
        params: list[str] = []
        for name, value in (("dateFrom", date_from), ("dateTo", date_to), ("status", status)):
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be a non-empty string")
                params.append(f"{name}={value.strip()}")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
                raise ValueError("limit must be an integer between 1 and 100")
            params.append(f"limit={limit}")
        endpoint = f"{self.base_url}/competitions/{competition}/matches"
        if params:
            endpoint += "?" + "&".join(params)
        payload_bytes = self._transport(
            endpoint,
            {"Accept": "application/json", "X-Auth-Token": self.api_token},
            self.timeout_seconds,
        )
        try:
            payload = json.loads(payload_bytes)
        except (TypeError, json.JSONDecodeError) as error:
            raise FootballDataOrgPayloadError("response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise FootballDataOrgPayloadError("response must be a JSON object")
        return RawProviderResponse(
            endpoint, payload, hashlib.sha256(payload_bytes).hexdigest(), datetime.now(UTC)
        )


__all__ = [
    "FootballDataOrgAuthenticationError",
    "FootballDataOrgClient",
    "FootballDataOrgError",
    "FootballDataOrgPayloadError",
    "RawProviderResponse",
]
