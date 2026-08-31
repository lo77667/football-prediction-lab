"""Small, dependency-free RSS/Atom reader for auditable news ingestion."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class RSSFetchError(RuntimeError):
    """Base RSS fetching/parsing error."""


@dataclass(frozen=True)
class RSSItem:
    item_id: str
    title: str
    url: str
    published_at_utc: datetime | None
    summary: str


@dataclass(frozen=True)
class RSSBatch:
    feed_url: str
    items: tuple[RSSItem, ...]
    response_sha256: str
    fetched_at_utc: datetime


Transport = Callable[[str, float], bytes]


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/rss+xml, application/atom+xml, application/xml",
            "User-Agent": "football-prediction-lab/1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise RSSFetchError(f"RSS request failed: {type(error).__name__}") from error


def _text(element: ElementTree.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _first_child(
    element: ElementTree.Element, names: tuple[str, ...]
) -> ElementTree.Element | None:
    for child in list(element):
        if child.tag.rsplit("}", 1)[-1].lower() in names:
            return child
    return None


def parse_feed(feed_url: str, payload: bytes) -> RSSBatch:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise RSSFetchError("RSS response is not valid XML") from error
    entries = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
    ]
    items: list[RSSItem] = []
    for entry in entries:
        title = _text(_first_child(entry, ("title",)))
        link_element = _first_child(entry, ("link",))
        url = ""
        if link_element is not None:
            url = link_element.attrib.get("href", "") or _text(link_element)
        guid = _text(_first_child(entry, ("guid", "id"))) or url
        if not title or not url or not guid:
            continue
        published = _text(_first_child(entry, ("pubdate", "published", "updated")))
        summary = _text(_first_child(entry, ("description", "summary", "content")))
        items.append(
            RSSItem(
                hashlib.sha256(guid.encode("utf-8")).hexdigest()[:24],
                title,
                url,
                _published(published),
                summary,
            )
        )
    return RSSBatch(feed_url, tuple(items), hashlib.sha256(payload).hexdigest(), datetime.now(UTC))


class RSSClient:
    """Fetch RSS/Atom feeds with explicit network opt-in."""

    def __init__(
        self,
        *,
        allow_network: bool = False,
        timeout_seconds: float = 15.0,
        transport: Transport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.allow_network = allow_network
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _default_transport

    def fetch(self, feed_url: str) -> RSSBatch:
        if not isinstance(feed_url, str) or not feed_url.startswith(("https://", "http://")):
            raise ValueError("feed_url must be an HTTP(S) URL")
        if not self.allow_network and self._transport is _default_transport:
            raise RSSFetchError("RSS network access is disabled; pass allow_network=True")
        payload = self._transport(feed_url, self.timeout_seconds)
        if not isinstance(payload, bytes):
            raise RSSFetchError("transport must return bytes")
        return parse_feed(feed_url, payload)


__all__ = ["RSSBatch", "RSSClient", "RSSFetchError", "RSSItem", "parse_feed"]
