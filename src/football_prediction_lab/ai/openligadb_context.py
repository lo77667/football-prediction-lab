"""Build strictly pre-match AI context from an OpenLigaDB batch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from football_prediction_lab.source.openligadb import OpenLigaBatch, OpenLigaMatch

from .guardrails import AnalysisEvidence, AnalysisRequest


def build_pre_match_request(
    batch: OpenLigaBatch,
    match: OpenLigaMatch,
    *,
    as_of_utc: datetime,
) -> tuple[AnalysisRequest, dict[str, Any]]:
    """Return an evidence-backed request and context with no provider results."""

    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() != timedelta(0):
        raise ValueError("as_of_utc must be explicit UTC")
    observed_at = as_of_utc.astimezone(UTC)
    if match.kickoff_utc <= observed_at:
        raise ValueError("match must be upcoming at analysis cutoff")
    evidence_id = f"openligadb:{match.match_id}:{batch.response_sha256[:16]}"
    request = AnalysisRequest(
        match_id=str(match.match_id),
        kickoff_utc=match.kickoff_utc,
        as_of_utc=observed_at,
        evidence=(
            AnalysisEvidence(
                evidence_id=evidence_id,
                source_name="OpenLigaDB",
                source_url=batch.endpoint,
                captured_at_utc=batch.fetched_at_utc,
                content_sha256=batch.response_sha256,
            ),
        ),
    )
    context = {
        "league_shortcut": match.league_shortcut,
        "league_season": match.league_season,
        "match_id": str(match.match_id),
        "team1_id": match.team1.team_id,
        "team1_name": match.team1.name,
        "team2_id": match.team2.team_id,
        "team2_name": match.team2.name,
        "kickoff_utc": match.kickoff_utc.isoformat(),
        "source_response_sha256": batch.response_sha256,
    }
    return request, context
