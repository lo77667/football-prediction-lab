from datetime import UTC, datetime, timedelta

from football_prediction_lab.ingestion import ExternalSource, adapt_odds_payload

KICKOFF = datetime(2026, 8, 8, 19, tzinfo=UTC)


def _source(*, allowed_reuse: bool = True) -> ExternalSource:
    return ExternalSource(
        source_name="fixture-odds-source",
        provider="test-provider",
        endpoint_or_dataset_id="fixture-only",
        source_version="v1",
        license_name="test-only",
        allowed_reuse=allowed_reuse,
        retrieved_at_utc=KICKOFF - timedelta(hours=1),
        request_or_snapshot_id="request-1",
        input_sha256="a" * 64,
        schema_version="odds-v1",
        retention_policy="test-only",
    )


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "request_or_snapshot_id": "snapshot-1",
        "snapshot_version": "v1",
        "match_id": "match-1",
        "captured_at_utc": "2026-08-08T18:00:00Z",
        "market": "btts",
        "market_definition": "Both teams to score",
        "selection": "yes",
        "decimal_odds": 2.0,
        "odds_type": "pre_match",
    }
    row.update(overrides)
    return row


def test_adapter_accepts_only_source_backed_pre_match_fixture() -> None:
    result = adapt_odds_payload([_row()], source=_source(), event_kickoffs_utc={"match-1": KICKOFF})
    assert result.accepted_rows == 1
    assert result.rejected_by_reason == {}
    assert result.records[0].kickoff_utc == KICKOFF
    assert result.records[0].input_sha256 == result.input_sha256


def test_adapter_rejects_post_kickoff_and_unknown_event() -> None:
    result = adapt_odds_payload(
        [
            _row(captured_at_utc="2026-08-08T19:00:00Z"),
            _row(match_id="unknown"),
        ],
        source=_source(),
        event_kickoffs_utc={"match-1": KICKOFF},
    )
    assert result.accepted_rows == 0
    assert result.raw_rows == 2
    assert result.rejected_by_reason == {
        "invalid_row:ValidationError": 1,
        "invalid_row:ValueError": 1,
    }


def test_adapter_rejects_unknown_fields_and_non_reusable_source() -> None:
    unknown = adapt_odds_payload(
        [_row(unexpected="value")], source=_source(), event_kickoffs_utc={"match-1": KICKOFF}
    )
    assert unknown.accepted_rows == 0
    assert unknown.rejected_by_reason == {"invalid_row:ValueError": 1}

    restricted = adapt_odds_payload(
        [_row()], source=_source(allowed_reuse=False), event_kickoffs_utc={"match-1": KICKOFF}
    )
    assert restricted.accepted_rows == 0
    assert restricted.rejected_by_reason == {"source_not_reusable": 1}
