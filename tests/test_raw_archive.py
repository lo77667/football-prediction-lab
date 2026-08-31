from datetime import UTC, datetime

import pytest

from football_prediction_lab.source.raw_archive import RawArchive


def test_raw_archive_is_content_addressed_and_writes_metadata(tmp_path) -> None:
    fetched_at = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    archive = RawArchive(tmp_path / "raw")
    first = archive.store(
        provider="test",
        endpoint="https://example.com/data",
        payload=b"{}",
        fetched_at_utc=fetched_at,
    )
    second = archive.store(
        provider="test",
        endpoint="https://example.com/data",
        payload=b"{}",
        fetched_at_utc=fetched_at,
    )
    assert first.payload_path == second.payload_path
    assert first.payload_path.read_bytes() == b"{}"
    metadata = first.metadata_path.read_text(encoding="utf-8")
    assert first.payload_sha256 in metadata
    assert "fetched_at_utc" in metadata


def test_raw_archive_rejects_secret_metadata(tmp_path) -> None:
    with pytest.raises(ValueError, match="secret"):
        RawArchive(tmp_path / "raw").store(
            provider="test",
            endpoint="https://example.com/data",
            payload=b"{}",
            extra_metadata={"api_key": "do-not-store"},
        )
