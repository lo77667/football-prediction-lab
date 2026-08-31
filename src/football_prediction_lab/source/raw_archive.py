"""Content-addressed archive for raw provider responses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RawArtifact:
    provider: str
    endpoint: str
    fetched_at_utc: datetime
    payload_sha256: str
    payload_path: Path
    metadata_path: Path


class RawArchive:
    """Write raw bytes once, addressed by SHA-256, plus non-secret metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        *,
        provider: str,
        endpoint: str,
        payload: bytes,
        fetched_at_utc: datetime | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> RawArtifact:
        if not provider or not endpoint:
            raise ValueError("provider and endpoint must be non-empty")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        fetched = (fetched_at_utc or datetime.now(UTC)).astimezone(UTC)
        digest = hashlib.sha256(payload).hexdigest()
        provider_dir = self.root / provider.replace("/", "_")
        provider_dir.mkdir(parents=True, exist_ok=True)
        payload_path = provider_dir / f"{digest}.bin"
        metadata_path = provider_dir / f"{digest}.json"
        if not payload_path.exists():
            payload_path.write_bytes(payload)
        metadata: dict[str, Any] = {
            "provider": provider,
            "endpoint": endpoint,
            "fetched_at_utc": fetched.isoformat(),
            "payload_sha256": digest,
            "payload_bytes": len(payload),
        }
        if extra_metadata:
            forbidden = {"api_key", "api_token", "authorization", "x-auth-token"}
            if forbidden.intersection(extra_metadata):
                raise ValueError("secret-like metadata fields are not allowed")
            metadata["extra"] = extra_metadata
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return RawArtifact(provider, endpoint, fetched, digest, payload_path, metadata_path)


__all__ = ["RawArchive", "RawArtifact"]
