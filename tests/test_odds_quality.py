from datetime import UTC, datetime, timedelta

import pytest

from football_prediction_lab.evaluation.odds_quality import (
    profile_odds_quality,
    verify_quality_profile,
)
from football_prediction_lab.evaluation.odds_schema import OddsSnapshot

KICKOFF = datetime(2025, 8, 1, 12, tzinfo=UTC)


def make_snapshot(snapshot_id: str, captured_at: datetime) -> OddsSnapshot:
    return OddsSnapshot(
        snapshot_id=snapshot_id,
        match_id="m-1",
        match_kickoff_utc=KICKOFF,
        market="btts",
        market_definition="Both teams to score at least one goal",
        selection="yes",
        decimal_odds=2.0,
        captured_at=captured_at,
        source_name="source-a",
        source_version="v1",
        provenance_id="p-1",
        input_sha256="a" * 64,
        odds_type="pre_match",
        is_licensed_or_reusable=True,
    )


def test_profile_is_deterministic_and_counts_duplicate_identity() -> None:
    first = make_snapshot("s-1", KICKOFF - timedelta(hours=2))
    second = make_snapshot("s-2", KICKOFF - timedelta(hours=1))
    profile = profile_odds_quality([second, first, first])

    assert profile.rows == 3
    assert profile.unique_matches == 1
    assert profile.duplicate_identity_rows == 1
    assert profile.market_source_groups == 1
    assert profile.capture_min_utc == "2025-08-01T10:00:00+00:00"
    assert profile.capture_max_utc == "2025-08-01T11:00:00+00:00"
    assert profile.non_monotonic_match_captures == 1
    assert profile.profile_sha256 == profile_odds_quality([second, first, first]).profile_sha256


def test_verify_quality_profile_fails_closed_on_mismatch() -> None:
    first = make_snapshot("s-1", KICKOFF - timedelta(hours=2))
    expected = profile_odds_quality([first])
    assert verify_quality_profile([first], expected) == expected

    changed = expected.model_copy(update={"rows": 2})
    with pytest.raises(ValueError, match="does not match"):
        verify_quality_profile([first], changed)


def test_profile_empty_input_is_explicit() -> None:
    profile = profile_odds_quality([])
    assert profile.rows == 0
    assert profile.unique_matches == 0
    assert profile.capture_min_utc is None
    assert profile.capture_max_utc is None
