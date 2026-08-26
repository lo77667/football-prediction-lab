from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from football_prediction_lab.ingestion.local_csv import validate_manifest
from football_prediction_lab.shadow.contracts import ShadowPrediction, ShadowRun
from football_prediction_lab.shadow.ledger import ShadowLedger

RUNTIME_PROVENANCE_COLUMNS = frozenset({"source_provenance_id", "ingestion_run_id"})

TARGET_COLUMNS = frozenset(
    {
        "target",
        "result",
        "btts",
        "total_yellows_over_3_5",
        "home_goals",
        "away_goals",
        "home_yellows",
        "away_yellows",
        "fthg",
        "ftag",
        "ftr",
        "hs",
        "as",
        "hst",
        "ast",
        "hc",
        "ac",
        "hf",
        "af",
        "hy",
        "ay",
        "hr",
        "ar",
    }
)
PROBABILITY_COLUMNS = {"btts": "probability_btts", "cards": "probability_cards"}
MARKET_DEFINITIONS = {
    "btts": "both teams to score (BTTS)",
    "cards": "total yellow cards over 3.5",
}


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _source_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    marker = root / "SOURCE_COMMIT.txt"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else "unknown"


def _parse_utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("shadow timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _iso(value: Any) -> str:
    return _parse_utc(value).isoformat()


def _prediction_id(payload: dict[str, Any]) -> str:
    return _hash_json(payload)


def _row_feature_hash(row: pd.Series) -> str:
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if str(key).lower() in TARGET_COLUMNS or str(key) in RUNTIME_PROVENANCE_COLUMNS:
            continue
        if isinstance(value, pd.Timestamp):
            payload[str(key)] = _iso(value)
        elif pd.isna(value):
            payload[str(key)] = None
        else:
            payload[str(key)] = value.item() if hasattr(value, "item") else value
    return _hash_json(payload)


def _policy_metadata(policy: dict[str, Any], market: str) -> tuple[str, str, str]:
    details = policy["markets"][market]
    return (
        str(details["feature_version"]),
        str(details["model_version"]),
        str(details["selected_candidate_policy"]),
    )


def _rejection(rejections: dict[str, int], reason: str) -> None:
    rejections[reason] = rejections.get(reason, 0) + 1


def run_shadow(
    *,
    manifest_path: Path,
    as_of_utc: datetime,
    run_id: str,
    output_root: Path,
    policy_path: Path,
    training_cutoff: datetime | None = None,
    code_commit: str | None = None,
) -> dict[str, Any]:
    """Issue deterministic pre-match predictions and append them idempotently."""

    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    as_of = as_of_utc.astimezone(UTC)
    training_cutoff = (training_cutoff or (as_of - timedelta(seconds=1))).astimezone(UTC)
    if training_cutoff >= as_of:
        raise ValueError("training_cutoff must precede as_of_utc")
    manifest = validate_manifest(manifest_path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != "cycle36-future-holdout-policy-v1":
        raise ValueError("unsupported shadow policy schema")
    if policy.get("policy_version") != "cycle36-future-2627-policy-v1":
        raise ValueError("shadow mode requires the locked Cycle 36 policy")
    if policy.get("commercial_release") is not False:
        raise ValueError("shadow mode requires commercial_release=false")
    if set(policy.get("markets", {})) != {"btts", "cards"}:
        raise ValueError("shadow mode requires the locked BTTS and cards markets")
    for market in ("btts", "cards"):
        if policy["markets"][market].get("selected_candidate_policy") != "constant_train_rate":
            raise ValueError("shadow mode forbids selection, tuning, and calibration")
    if "2526" in {str(value) for value in policy.get("development_seasons", [])}:
        raise ValueError("2526 cannot be included in shadow policy development seasons")
    if policy.get("future_holdout") != ["2627"]:
        raise ValueError("shadow mode requires 2627 to remain reserved")

    input_path = Path(manifest["output_path"])
    frame = pd.read_csv(input_path)
    forbidden = sorted(
        TARGET_COLUMNS.intersection({str(column).lower() for column in frame.columns})
    )
    if forbidden:
        raise ValueError(f"shadow input contains target/post-match columns: {forbidden}")
    required = {"match_id", "kickoff_utc"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"shadow input is missing required columns: {missing}")
    frame["kickoff_utc"] = pd.to_datetime(frame["kickoff_utc"], utc=True, errors="coerce")
    if frame["kickoff_utc"].isna().any():
        raise ValueError("shadow input contains invalid kickoff_utc")
    if frame["match_id"].astype(str).duplicated().any():
        raise ValueError("shadow input contains duplicate match_id values")

    started = datetime.now(UTC)
    predictions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    rejection_counts: dict[str, int] = {}
    for _, row in frame.sort_values(["kickoff_utc", "match_id"], kind="mergesort").iterrows():
        match_id = str(row["match_id"])
        kickoff = row["kickoff_utc"].to_pydatetime().astimezone(UTC)
        if kickoff <= as_of:
            skipped.append({"match_id": match_id, "reason": "kickoff_not_in_future"})
            _rejection(rejection_counts, "kickoff_not_in_future")
            continue
        if "available_at_utc" not in row.index or pd.isna(row["available_at_utc"]):
            skipped.append({"match_id": match_id, "reason": "missing_available_at_utc"})
            _rejection(rejection_counts, "missing_available_at_utc")
            continue
        available = _parse_utc(row["available_at_utc"]).to_pydatetime()
        if available > as_of:
            skipped.append({"match_id": match_id, "reason": "features_not_available_at_as_of"})
            _rejection(rejection_counts, "features_not_available_at_as_of")
            continue
        season_value = str(row.get("season", "")).strip()
        if season_value.endswith(".0"):
            season_value = season_value[:-2]
        if season_value == "2627":
            skipped.append({"match_id": match_id, "reason": "future_holdout_reserved"})
            _rejection(rejection_counts, "future_holdout_reserved")
            continue
        feature_hash = _row_feature_hash(row)
        for market in ("btts", "cards"):
            probability_column = PROBABILITY_COLUMNS[market]
            if probability_column not in row.index or pd.isna(row[probability_column]):
                skipped.append(
                    {"match_id": match_id, "market": market, "reason": "missing_frozen_probability"}
                )
                _rejection(rejection_counts, f"missing_frozen_probability_{market}")
                continue
            probability = float(row[probability_column])
            if not 0.0 <= probability <= 1.0:
                skipped.append(
                    {"match_id": match_id, "market": market, "reason": "invalid_probability"}
                )
                _rejection(rejection_counts, f"invalid_probability_{market}")
                continue
            feature_version, model_version, policy_variant = _policy_metadata(policy, market)
            prediction_payload = {
                "match_id": match_id,
                "market": market,
                "policy_version": policy["policy_version"],
                "model_version": model_version,
                "feature_version": feature_version,
                "as_of_utc": as_of.isoformat(),
                "source_manifest_fingerprint": manifest["manifest_fingerprint"],
                "feature_provenance_hash": feature_hash,
                "probability": probability,
            }
            prediction = ShadowPrediction(
                prediction_id=_prediction_id(prediction_payload),
                match_id=match_id,
                market=market,
                market_definition=MARKET_DEFINITIONS[market],
                kickoff_utc=kickoff,
                issued_at_utc=as_of,
                as_of_utc=as_of,
                training_cutoff=training_cutoff,
                model_version=model_version,
                feature_version=feature_version,
                policy_version=policy["policy_version"],
                probability=probability,
                feature_provenance_hash=feature_hash,
                source_manifest_fingerprint=manifest["manifest_fingerprint"],
                selected_policy_variant=policy_variant,
            )
            predictions.append(prediction.model_dump(mode="json"))

    output_root = output_root.resolve()
    predictions_path = output_root / "predictions" / f"{run_id}.json"
    run_path = output_root / "runs" / f"{run_id}.json"
    ledger_path = output_root / "ledger" / "predictions.jsonl"
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": "cycle39-shadow-predictions-v1",
        "run_id": run_id,
        "as_of_utc": as_of.isoformat(),
        "training_cutoff": training_cutoff.isoformat(),
        "source_manifest_fingerprint": manifest["manifest_fingerprint"],
        "policy_version": policy["policy_version"],
        "commercial_release": False,
        "predictions": predictions,
        "skipped": skipped,
    }
    artifact_bytes = (
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if predictions_path.exists() and predictions_path.read_bytes() != artifact_bytes:
        raise ValueError("existing prediction artifact conflict: refusing mutation")
    if not predictions_path.exists():
        predictions_path.write_bytes(artifact_bytes)
    output_sha256 = hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    ledger = ShadowLedger(ledger_path)
    for record in predictions:
        ledger.append_prediction(ShadowPrediction.model_validate(record))
    ledger.verify()
    completed = datetime.now(UTC)
    run = ShadowRun(
        run_id=run_id,
        as_of_utc=as_of,
        started_at_utc=started,
        completed_at_utc=completed,
        source_manifest_fingerprint=manifest["manifest_fingerprint"],
        input_sha256=manifest["input_sha256"],
        feature_input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        code_commit=code_commit or _source_commit(Path(__file__).resolve().parents[3]),
        policy_version=policy["policy_version"],
        model_version="cycle36-candidate-suite-v1",
        feature_version="cycle39-shadow-input-v1",
        training_cutoff=training_cutoff,
        rows_seen=len(frame),
        predictions_issued=len(predictions),
        rows_skipped=len({str(item["match_id"]) for item in skipped}),
        rejection_counts=dict(sorted(rejection_counts.items())),
        status="completed",
        output_sha256=output_sha256,
        ledger_sha256=ledger.sha256(),
    )
    run_dict = run.as_audit_dict()
    if run_path.exists():
        existing_run = json.loads(run_path.read_text(encoding="utf-8"))
        runtime_fields = {"started_at_utc", "completed_at_utc"}
        if {key: value for key, value in existing_run.items() if key not in runtime_fields} != {
            key: value for key, value in run_dict.items() if key not in runtime_fields
        }:
            raise ValueError("existing run artifact conflict: refusing mutation")
        run_dict = existing_run
    else:
        run_path.write_text(json.dumps(run_dict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "predictions_path": str(predictions_path),
        "run_path": str(run_path),
        "ledger_path": str(ledger_path),
        "run": run_dict,
        "artifact": artifact,
    }
