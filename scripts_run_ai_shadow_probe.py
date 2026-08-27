"""Run one opt-in, pre-match AI analysis using a live OpenLigaDB fixture."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from football_prediction_lab.ai import (
    AIAnalysisError,
    AnalysisEvidence,
    AnalysisRequest,
    OpenAIJSONAnalyzer,
)
from football_prediction_lab.source import OpenLigaDBClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--model", default="gpt-5-mini")
    args = parser.parse_args()
    if not args.allow_network:
        print(json.dumps({"status": "deferred_network_disabled", "commercial_release": False}))
        return 0

    as_of = datetime.now(UTC)
    batch = OpenLigaDBClient(
        allow_network=True,
        timeout_seconds=10.0,
        min_interval_seconds=1.0,
    ).fetch_league_season("pl", 2026)
    upcoming = [match for match in batch.matches if match.kickoff_utc > as_of]
    if not upcoming:
        print(json.dumps({"status": "no_upcoming_fixture", "commercial_release": False}))
        return 0
    match = upcoming[0]
    request = AnalysisRequest(
        match_id=str(match.match_id),
        kickoff_utc=match.kickoff_utc,
        as_of_utc=as_of,
        evidence=(
            AnalysisEvidence(
                evidence_id=f"openligadb-{match.match_id}",
                source_name="OpenLigaDB",
                source_url=batch.endpoint,
                captured_at_utc=batch.fetched_at_utc,
                content_sha256=batch.response_sha256,
            ),
        ),
    )
    analyzer = OpenAIJSONAnalyzer(model=args.model)
    try:
        result = analyzer.analyze(
            request,
            context={
                "league_shortcut": match.league_shortcut,
                "league_season": match.league_season,
                "team1_id": match.team1.team_id,
                "team1_name": match.team1.name,
                "team2_id": match.team2.team_id,
                "team2_name": match.team2.name,
                "kickoff_utc": match.kickoff_utc.isoformat(),
                "finished": False,
            },
        )
    except AIAnalysisError as error:
        print(
            json.dumps(
                {
                    "status": "quarantined",
                    "reason_code": str(error).split(" ")[0],
                    "prediction_issued": False,
                    "raw_provider_payload_saved": False,
                    "commercial_release": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "passed",
                "provider": "OpenLigaDB",
                "model": args.model,
                "match_id": result.match_id,
                "analysis_status": result.status,
                "signal_count": len(result.signals),
                "evidence_ids": sorted(
                    {
                        evidence_id
                        for signal in result.signals
                        for evidence_id in signal.evidence_ids
                    }
                ),
                "as_of_utc": result.as_of_utc.isoformat(),
                "commercial_release": False,
                "prediction_issued": False,
                "raw_provider_payload_saved": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
