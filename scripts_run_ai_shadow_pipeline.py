"""Run bounded local OpenLigaDB ingestion and optional guarded AI analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from football_prediction_lab.ai import AIAnalysisError, OpenAIJSONAnalyzer, build_pre_match_request
from football_prediction_lab.source import OpenLigaDBClient, OpenLigaDBShadowIngestor
from football_prediction_lab.storage import SQLiteStore

ROOT = Path(__file__).resolve().parent


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-ai", action="store_true")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--output-root", type=Path, default=ROOT / "reports" / "local_shadow")
    parser.add_argument("--max-fixtures", type=int, default=1)
    args = parser.parse_args()
    if args.max_fixtures < 1:
        parser.error("--max-fixtures must be positive")
    if not args.allow_network:
        print(json.dumps({"status": "deferred_network_disabled", "commercial_release": False}))
        return 0

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    database = output_root / "shadow.sqlite3"
    client = OpenLigaDBClient(
        allow_network=True,
        timeout_seconds=10.0,
        min_interval_seconds=1.0,
        cache_ttl_seconds=900.0,
    )
    store = SQLiteStore(database)
    as_of = datetime.now(UTC)
    ingestion = OpenLigaDBShadowIngestor(client=client, store=store)
    ingest_result = ingestion.run_once(as_of_utc=as_of)
    batch = client.fetch_league_season("pl", 2026)
    upcoming = [match for match in batch.matches if match.kickoff_utc > as_of][: args.max_fixtures]
    accepted = 0
    quarantined = 0
    analysis_ids: list[str] = []
    quarantine_reasons: list[str] = []

    if args.allow_ai:
        analyzer = OpenAIJSONAnalyzer(model=args.model)
        for match in upcoming:
            request, context = build_pre_match_request(batch, match, as_of_utc=as_of)
            try:
                analysis = analyzer.analyze(request, context=context)
            except AIAnalysisError as error:
                quarantined += 1
                quarantine_reasons.append(type(error).__name__)
                store.record_audit(
                    event_type="ai_analysis_quarantined",
                    reference_id=str(match.match_id),
                    created_at_utc=request.as_of_utc.isoformat().replace("+00:00", "Z"),
                    payload={
                        "match_id": str(match.match_id),
                        "model_name": args.model,
                        "reason_code": type(error).__name__,
                        "commercial_release": False,
                    },
                )
                continue
            output = analysis.model_dump(mode="json")
            analysis_id = hashlib.sha256(
                _canonical(
                    {
                        "match_id": analysis.match_id,
                        "as_of_utc": analysis.as_of_utc.isoformat(),
                        "model_name": args.model,
                        "output": output,
                    }
                )
            ).hexdigest()
            if store.record_ai_analysis(
                analysis_id=analysis_id,
                match_id=analysis.match_id,
                as_of_utc=analysis.as_of_utc.isoformat().replace("+00:00", "Z"),
                model_name=args.model,
                schema_version=analysis.schema_version,
                status=analysis.status,
                output=output,
                source_manifest_fingerprint=ingest_result.manifest_fingerprint,
                created_at_utc=as_of.isoformat().replace("+00:00", "Z"),
            ):
                accepted += 1
                analysis_ids.append(analysis_id)
    summary = {
        "status": "completed",
        "network_opt_in": True,
        "ai_opt_in": args.allow_ai,
        "model": args.model if args.allow_ai else None,
        "ingestion": ingest_result.__dict__,
        "fixtures_considered_for_ai": len(upcoming),
        "ai_analyses_stored": accepted,
        "ai_analyses_quarantined": quarantined,
        "analysis_ids": analysis_ids,
        "quarantine_reasons": sorted(quarantine_reasons),
        "prediction_issued": False,
        "telegram_enabled": False,
        "commercial_release": False,
    }
    summary_path = output_root / "ai_shadow_latest.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {**summary, "summary_path": str(summary_path)},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
