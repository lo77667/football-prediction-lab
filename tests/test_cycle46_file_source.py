from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from football_prediction_lab.source import LocalJsonlSource

NOW = "2025-01-01T12:00:00+00:00"


def _row(**overrides: object) -> dict[str, object]:
    value = {
        "match_id": "m1",
        "market": "btts",
        "kickoff_utc": "2025-01-02T12:00:00+00:00",
        "observed_at_utc": NOW,
        "source_version": "fixture-v1",
    }
    value.update(overrides)
    return value


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8"
    )


def test_local_source_accepts_sorted_pre_match_rows_and_hashes_bytes(tmp_path: Path) -> None:
    path = tmp_path / "source.jsonl"
    _write(path, [_row(match_id="m2"), _row(match_id="m1")])
    batch = LocalJsonlSource(path, source_version="fixture-v1").read(
        as_of_utc=__import__("datetime").datetime.fromisoformat(NOW)
    )
    assert [row.match_id for row in batch.rows] == ["m1", "m2"]
    assert not batch.quarantined
    assert batch.input_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_quarantines_duplicate_stale_late_and_schema_rows(tmp_path: Path) -> None:
    path = tmp_path / "source.jsonl"
    _write(
        path,
        [
            _row(),
            _row(),
            _row(match_id="late", kickoff_utc="2025-01-01T11:00:00+00:00"),
            _row(match_id="stale", observed_at_utc="2024-12-01T12:00:00+00:00"),
            {"match_id": "bad", "market": "btts"},
        ],
    )
    batch = LocalJsonlSource(path, source_version="fixture-v1").read(
        as_of_utc=__import__("datetime").datetime.fromisoformat(NOW)
    )
    assert [row.match_id for row in batch.rows] == ["m1"]
    assert len(batch.quarantined) == 4
    assert any("duplicate_match_market" in row.reason for row in batch.quarantined)
    assert any("available_after_kickoff" in row.reason for row in batch.quarantined)


@pytest.mark.parametrize(
    "value",
    ["2025-01-01T12:00:00", "2025-01-01T12:00:00+01:00"],
)
def test_rejects_ambiguous_or_non_utc_timestamps(tmp_path: Path, value: str) -> None:
    path = tmp_path / "source.jsonl"
    _write(path, [_row(observed_at_utc=value)])
    batch = LocalJsonlSource(path, source_version="fixture-v1").read(
        as_of_utc=__import__("datetime").datetime.fromisoformat(NOW)
    )
    assert len(batch.rows) == 0
    assert "timestamp must be explicit UTC" in batch.quarantined[0].reason


def test_rejects_extra_fields_and_source_version_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "source.jsonl"
    _write(path, [_row(extra="blocked"), _row(source_version="other")])
    batch = LocalJsonlSource(path, source_version="fixture-v1").read(
        as_of_utc=__import__("datetime").datetime.fromisoformat(NOW)
    )
    assert len(batch.rows) == 0
    assert all("mismatch" in row.reason for row in batch.quarantined)


def test_rejects_naive_as_of(tmp_path: Path) -> None:
    path = tmp_path / "source.jsonl"
    _write(path, [_row()])
    with pytest.raises(ValueError, match="timezone-aware"):
        LocalJsonlSource(path, source_version="fixture-v1").read(
            as_of_utc=__import__("datetime").datetime(2025, 1, 1, 12)
        )
