import json

import pytest

from football_prediction_lab.source.freepublicapis_catalog import (
    FreePublicAPIsCatalogClient,
    FreePublicAPIsError,
)


def test_catalog_client_fetches_and_searches_locally() -> None:
    payload = json.dumps(
        [
            {
                "id": 1,
                "title": "Football Data API",
                "description": "matches and standings",
                "documentation": "https://example.com/docs",
                "source": "https://example.com",
                "health": 90,
            },
            {"id": 2, "title": "Weather API", "description": "forecasts", "health": 80},
        ]
    ).encode()
    calls: list[str] = []

    def transport(url: str, _: float) -> bytes:
        calls.append(url)
        return payload

    client = FreePublicAPIsCatalogClient(transport=transport)
    response = client.fetch(limit=20, sort="best")
    matches = client.search(response, "football")
    assert len(response.entries) == 2
    assert len(matches) == 1
    assert matches[0].source == "https://example.com"
    assert "limit=20" in calls[0]
    assert "sort=best" in calls[0]


def test_catalog_client_rejects_invalid_response() -> None:
    with pytest.raises(FreePublicAPIsError):
        FreePublicAPIsCatalogClient(transport=lambda _url, _timeout: b"{}").fetch()
