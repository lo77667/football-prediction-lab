"""Deterministic, fail-closed ingestion for authorized local CSV files."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from football_prediction_lab.data.provenance import sha256_file
from football_prediction_lab.ingestion.adapter import DataSourceAdapter
from football_prediction_lab.ingestion.contracts import IngestionRun, SourceRecord

SCHEMA_VERSION = "cycle38-match-v1"
POST_MATCH_COLUMNS = frozenset(
    {
        "btts",
        "total_yellows_over_3_5",
        "home_goals",
        "away_goals",
        "home_yellows",
        "away_yellows",
        "result",
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
REQUIRED_CANONICAL_COLUMNS = (
    "match_id",
    "season",
    "competition",
    "home_team",
    "away_team",
    "kickoff_utc",
    "source_provenance_id",
    "ingestion_run_id",
    "record_version",
)


@dataclass(frozen=True)
class IngestionResult:
    """Paths and the JSON-safe manifest produced by one ingestion run."""

    manifest: dict[str, Any]
    manifest_path: Path
    normalized_path: Path
    quarantine_path: Path
    raw_path: Path


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _parse_aware(value: Any, *, source_timezone: str | None = None) -> pd.Timestamp | None:
    if pd.isna(value):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        if source_timezone is None:
            return None
        timestamp = timestamp.tz_localize(ZoneInfo(source_timezone))
    return timestamp.tz_convert("UTC")


def _column_lookup(columns: list[str]) -> dict[str, str]:
    return {str(column).strip().lower(): str(column) for column in columns}


def _resolve_column(lookup: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def _read_datetime_column(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    source_timezone: str | None,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    kickoff_column = _resolve_column(lookup, "kickoff_utc")
    if kickoff_column is not None:
        values = []
        for index, value in frame[kickoff_column].items():
            parsed = _parse_aware(value)
            values.append(parsed)
            if parsed is None:
                issues.append({"row": int(index), "reason": "kickoff_timezone_or_parse_failure"})
        return pd.Series(values, index=frame.index, dtype="datetime64[ns, UTC]"), issues

    date_column = _resolve_column(lookup, "date")
    time_column = _resolve_column(lookup, "time")
    if date_column is None or time_column is None:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]"), [
            {"row": None, "reason": "missing_kickoff_utc_or_date_time"}
        ]
    if source_timezone is None:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]"), [
            {"row": None, "reason": "source_timezone_required_for_date_time"}
        ]
    values = []
    for index, (date_value, time_value) in frame[[date_column, time_column]].iterrows():
        parsed = _parse_aware(f"{date_value} {time_value}", source_timezone=source_timezone)
        values.append(parsed)
        if parsed is None:
            issues.append({"row": int(index), "reason": "date_time_parse_failure"})
    return pd.Series(values, index=frame.index, dtype="datetime64[ns, UTC]"), issues


def _reject_column_names(frame: pd.DataFrame) -> list[dict[str, Any]]:
    lookup = _column_lookup(list(frame.columns))
    found = sorted(POST_MATCH_COLUMNS.intersection(lookup))
    if not found:
        return []
    return [{"row": None, "reason": "post_match_column_in_pre_match", "columns": found}]


def _expand_file_level_issues(
    issues: list[dict[str, Any]], indices: pd.Index
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for issue in issues:
        if issue.get("row") is None:
            expanded.extend({**issue, "row": int(index)} for index in indices)
        else:
            expanded.append(issue)
    return expanded


def _safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [str(column).strip() for column in result.columns]
    return result


class LocalCsvAdapter(DataSourceAdapter):
    """Adapter for a user-authorized local CSV with no network access."""

    def __init__(
        self,
        input_path: Path,
        *,
        run_id: str,
        source_name: str,
        source_version: str,
        license_or_usage_policy: str,
        source_timezone: str | None = None,
        season: str = "unknown",
        competition: str = "unknown",
        code_commit: str = "unknown",
        max_rejection_rate: float = 0.25,
    ) -> None:
        self.input_path = input_path.resolve()
        self.run_id = run_id
        self.source_name = source_name
        self.source_version = source_version
        self.license_or_usage_policy = license_or_usage_policy
        self.source_timezone = source_timezone
        self.season = season
        self.competition = competition
        self.code_commit = code_commit
        self.max_rejection_rate = max_rejection_rate
        self.input_sha256 = sha256_file(self.input_path)
        self.provenance_id = f"{source_name}:{self.input_sha256[:16]}"
        self._raw_frame: pd.DataFrame | None = None
        self._normalized_frame: pd.DataFrame | None = None
        self._quarantine: list[dict[str, Any]] = []

    def discover(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_version": self.source_version,
            "input_path": str(self.input_path),
            "input_sha256": self.input_sha256,
            "license_or_usage_policy": self.license_or_usage_policy,
        }

    def fetch(self) -> pd.DataFrame:
        if not self.input_path.exists():
            raise FileNotFoundError(f"authorized local CSV not found: {self.input_path}")
        self._raw_frame = pd.read_csv(self.input_path)
        return self._raw_frame.copy()

    def normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        source = _safe_frame(frame)
        lookup = _column_lookup(list(source.columns))
        match_id_column = _resolve_column(lookup, "match_id")
        home_column = _resolve_column(lookup, "home_team", "hometeam")
        away_column = _resolve_column(lookup, "away_team", "awayteam")
        season_column = _resolve_column(lookup, "season")
        competition_column = _resolve_column(lookup, "competition", "league")
        record_version_column = _resolve_column(lookup, "record_version")
        kickoff, time_issues = _read_datetime_column(
            source,
            lookup,
            source_timezone=self.source_timezone,
        )
        self._quarantine.extend(_expand_file_level_issues(time_issues, source.index))
        self._quarantine.extend(
            _expand_file_level_issues(_reject_column_names(source), source.index)
        )
        if match_id_column is None:
            self._quarantine.append({"row": None, "reason": "missing_match_id"})
        if home_column is None or away_column is None:
            self._quarantine.append({"row": None, "reason": "missing_team_columns"})
        result = pd.DataFrame(index=source.index)
        result["match_id"] = source[match_id_column].astype("string") if match_id_column else ""
        result["season"] = (
            source[season_column].astype("string") if season_column else str(self.season)
        )
        result["competition"] = (
            source[competition_column].astype("string")
            if competition_column
            else str(self.competition)
        )
        result["home_team"] = source[home_column].astype("string") if home_column else ""
        result["away_team"] = source[away_column].astype("string") if away_column else ""
        result["kickoff_utc"] = kickoff
        result["source_provenance_id"] = self.provenance_id
        result["ingestion_run_id"] = self.run_id
        result["record_version"] = (
            pd.to_numeric(source[record_version_column], errors="coerce")
            if record_version_column
            else 1
        )
        available_column = _resolve_column(lookup, "available_at_utc")
        if available_column:
            available_values = []
            for index, value in source[available_column].items():
                parsed = _parse_aware(value)
                available_values.append(parsed)
                if parsed is None and not pd.isna(value):
                    self._quarantine.append(
                        {"row": int(index), "reason": "available_at_timezone_or_parse_failure"}
                    )
            result["available_at_utc"] = pd.Series(
                available_values, index=source.index, dtype="datetime64[ns, UTC]"
            )
        self._normalized_frame = result
        return result.copy()

    def validate(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        quarantine = list(self._quarantine)
        working = frame.copy()
        for index, row in working.iterrows():
            reasons: list[str] = []
            if pd.isna(row["match_id"]) or not str(row["match_id"]).strip():
                reasons.append("missing_match_id")
            if pd.isna(row["home_team"]) or not str(row["home_team"]).strip():
                reasons.append("empty_home_team")
            if pd.isna(row["away_team"]) or not str(row["away_team"]).strip():
                reasons.append("empty_away_team")
            if (
                str(row["home_team"]).strip() == str(row["away_team"]).strip()
                and str(row["home_team"]).strip()
            ):
                reasons.append("same_home_away_team")
            if pd.isna(row["kickoff_utc"]):
                reasons.append("invalid_kickoff_utc")
            if not str(row["season"]).strip() or str(row["season"]).lower() == "nan":
                reasons.append("invalid_season")
            if not str(row["competition"]).strip() or str(row["competition"]).lower() == "nan":
                reasons.append("invalid_competition")
            record_version = row["record_version"]
            if (
                pd.isna(record_version)
                or int(record_version) < 1
                or float(record_version) != int(record_version)
            ):
                reasons.append("invalid_record_version")
            available = row.get("available_at_utc")
            if available is not None and not pd.isna(available):
                parsed_available = _parse_aware(available)
                if parsed_available is None:
                    reasons.append("available_at_timezone_or_parse_failure")
                elif parsed_available > row["kickoff_utc"]:
                    reasons.append("available_after_kickoff")
            if reasons:
                quarantine.append({"row": int(index), "reason": ";".join(reasons)})
        duplicate_ids = working["match_id"].astype("string").duplicated(keep=False)
        for index in working.index[duplicate_ids.fillna(False)]:
            quarantine.append({"row": int(index), "reason": "duplicate_match_id_in_file"})
        rejected_rows = {item["row"] for item in quarantine if item.get("row") is not None}
        accepted = working.loc[~working.index.isin(rejected_rows)].copy()
        accepted["record_version"] = accepted["record_version"].astype(int)
        accepted = accepted.sort_values(["kickoff_utc", "match_id"], kind="mergesort").reset_index(
            drop=True
        )
        return accepted, quarantine

    def write_immutable_raw(self, destination: Path) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_file(destination) != self.input_sha256:
            raise RuntimeError(f"immutable raw collision with different content: {destination}")
        if not destination.exists():
            shutil.copyfile(self.input_path, destination)
        return sha256_file(destination)

    def build_manifest(self, **metadata: Any) -> dict[str, Any]:
        return metadata


def _load_existing_manifests(manifests_dir: Path) -> list[dict[str, Any]]:
    values = []
    for path in sorted(manifests_dir.glob("*.json")):
        try:
            values.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return values


def ingest_file(
    input_path: Path,
    *,
    run_id: str,
    output_root: Path,
    source_name: str = "authorized_local_csv",
    source_version: str = "local-file-v1",
    license_or_usage_policy: str = "user-authorized-local-file; verify before redistribution",
    source_timezone: str | None = None,
    season: str = "unknown",
    competition: str = "unknown",
    code_commit: str = "unknown",
    max_rejection_rate: float = 0.25,
) -> IngestionResult:
    """Ingest one local CSV and write deterministic outputs plus audit evidence."""

    if not 0 <= max_rejection_rate <= 1:
        raise ValueError("max_rejection_rate must be between 0 and 1")
    adapter = LocalCsvAdapter(
        input_path,
        run_id=run_id,
        source_name=source_name,
        source_version=source_version,
        license_or_usage_policy=license_or_usage_policy,
        source_timezone=source_timezone,
        season=season,
        competition=competition,
        code_commit=code_commit,
        max_rejection_rate=max_rejection_rate,
    )
    raw = adapter.fetch()
    normalized = adapter.normalize(raw)
    accepted, quarantine = adapter.validate(normalized)
    output_root = output_root.resolve()
    raw_path = output_root / "raw" / f"{adapter.input_sha256}.csv"
    normalized_path = output_root / "normalized" / f"{adapter.input_sha256}.csv"
    processed_path = output_root / "processed" / f"{adapter.input_sha256}.csv"
    quarantine_path = output_root / "quarantine" / f"{run_id}.json"
    manifest_path = output_root / "manifests" / f"{run_id}.json"
    registry_path = output_root / "manifests" / "match_registry.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    adapter.write_immutable_raw(raw_path)
    existing_manifests = _load_existing_manifests(manifest_path.parent)
    conflict_ids = set()
    for previous in existing_manifests:
        if (
            previous.get("source", {}).get("source_name") == source_name
            and previous.get("input_sha256") != adapter.input_sha256
        ):
            conflict_ids.update(previous.get("accepted_match_ids", []))
    if conflict_ids:
        for index, match_id in accepted["match_id"].items():
            if str(match_id) in conflict_ids:
                quarantine.append(
                    {"row": int(index), "reason": "existing_match_id_different_source_hash"}
                )
        accepted = accepted.loc[~accepted["match_id"].astype(str).isin(conflict_ids)].copy()
    now_started = _now()
    accepted.to_csv(normalized_path, index=False, lineterminator="\n")
    accepted.to_csv(processed_path, index=False, lineterminator="\n")
    output_hash = sha256_file(normalized_path)
    rows_read = len(raw)
    rejected_row_indices = {
        int(item["row"])
        for item in quarantine
        if item.get("row") is not None and int(item["row"]) in raw.index
    }
    rows_quarantined = len(rejected_row_indices)
    rejection_rate = rows_quarantined / rows_read if rows_read else 0.0
    quarantine_payload = {
        "schema_version": "cycle38-quarantine-v1",
        "run_id": run_id,
        "sample_limit": 100,
        "rows_quarantined": rows_quarantined,
        "rejection_counts_by_reason": pd.Series(
            [item["reason"] for item in quarantine], dtype="string"
        )
        .value_counts()
        .sort_index()
        .to_dict(),
        "sample": quarantine[:100],
    }
    quarantine_path.write_text(
        json.dumps(quarantine_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    status = "failed" if rejection_rate > max_rejection_rate else "completed"
    if status == "completed" and len(accepted) == 0 and rows_quarantined:
        status = "quarantined"
    completed = _now()
    run = IngestionRun(
        run_id=run_id,
        started_at_utc=now_started,
        completed_at_utc=completed,
        source_name=source_name,
        source_version=source_version,
        code_commit=code_commit,
        input_hash=adapter.input_sha256,
        output_hash=output_hash,
        rows_read=rows_read,
        rows_accepted=len(accepted),
        rows_quarantined=rows_quarantined,
        status=status,
        error_summary=sorted({str(item["reason"]) for item in quarantine}),
    )
    source = SourceRecord(
        source_name=source_name,
        source_version=source_version,
        retrieved_at_utc=now_started,
        input_path=str(input_path.resolve()),
        input_sha256=adapter.input_sha256,
        license_or_usage_policy=license_or_usage_policy,
        schema_version=SCHEMA_VERSION,
        row_count=rows_read,
    )
    manifest = {
        "schema_version": "cycle38-ingestion-manifest-v1",
        "source": source.model_dump(mode="json"),
        "source_name": source_name,
        "source_version": source_version,
        "run": run.model_dump(mode="json"),
        "input_path": str(input_path.resolve()),
        "input_sha256": adapter.input_sha256,
        "output_path": str(normalized_path),
        "processed_output_path": str(processed_path),
        "raw_path": str(raw_path),
        "quarantine_path": str(quarantine_path),
        "manifest_path": str(manifest_path),
        "season_values": sorted(accepted["season"].astype(str).unique().tolist()),
        "accepted_match_ids": accepted["match_id"].astype(str).tolist(),
        "kickoff_utc_min": None if accepted.empty else str(accepted["kickoff_utc"].min()),
        "kickoff_utc_max": None if accepted.empty else str(accepted["kickoff_utc"].max()),
        "timezone": "UTC",
        "rejection_rate": rejection_rate,
        "max_rejection_rate": max_rejection_rate,
        "rejection_counts_by_reason": quarantine_payload["rejection_counts_by_reason"],
        "duplicate_count": sum(
            1 for item in quarantine if item["reason"] == "duplicate_match_id_in_file"
        ),
        "timezone_failure_count": sum(
            1 for item in quarantine if "timezone" in item["reason"] or "kickoff" in item["reason"]
        ),
        "deterministic_sort": ["kickoff_utc", "match_id"],
        "pre_match_target_columns_forbidden": sorted(POST_MATCH_COLUMNS),
        "generated_at_utc": completed.isoformat(),
    }
    stable_manifest = dict(manifest)
    stable_manifest.pop("generated_at_utc", None)
    stable_manifest["run"] = dict(stable_manifest["run"])
    stable_manifest["run"].pop("started_at_utc", None)
    stable_manifest["run"].pop("completed_at_utc", None)
    stable_manifest["source"] = dict(stable_manifest["source"])
    stable_manifest["source"].pop("retrieved_at_utc", None)
    stable_manifest["manifest_fingerprint"] = _hash_json(stable_manifest)
    manifest["manifest_fingerprint"] = stable_manifest["manifest_fingerprint"]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    registry = {
        "schema_version": "cycle38-match-registry-v1",
        "match_ids": sorted(set(accepted["match_id"].astype(str).tolist())),
        "updated_by_run_id": run_id,
    }
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    result = IngestionResult(manifest, manifest_path, normalized_path, quarantine_path, raw_path)
    if status == "failed":
        raise RuntimeError(
            f"quarantine rate {rejection_rate:.3f} exceeds policy {max_rejection_rate:.3f}; "
            f"manifest preserved at {manifest_path}"
        )
    return result


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    """Validate manifest structure and every referenced local output hash."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run = IngestionRun.model_validate(manifest["run"])
    if run.input_hash != manifest["input_sha256"]:
        raise ValueError("manifest input hash mismatch")
    output_path = Path(manifest["output_path"])
    if not output_path.exists() or sha256_file(output_path) != run.output_hash:
        raise ValueError("manifest output hash mismatch or missing output")
    if (
        Path(manifest["raw_path"]).exists()
        and sha256_file(Path(manifest["raw_path"])) != run.input_hash
    ):
        raise ValueError("immutable raw hash mismatch")
    if run.rows_accepted + run.rows_quarantined < run.rows_read:
        raise ValueError("manifest row accounting is incomplete")
    if run.status == "failed" and manifest["rejection_rate"] <= manifest["max_rejection_rate"]:
        raise ValueError("failed run does not exceed rejection policy")
    return manifest


def replay_manifest(manifest_path: Path) -> dict[str, Any]:
    """Replay validation without writing a second version or reading targets."""

    manifest = validate_manifest(manifest_path)
    input_path = Path(manifest["input_path"])
    if not input_path.exists():
        raise FileNotFoundError(f"replay input is unavailable: {input_path}")
    if sha256_file(input_path) != manifest["input_sha256"]:
        raise ValueError("replay input hash differs from manifest")
    return {
        "replay": "passed",
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "input_sha256": manifest["input_sha256"],
        "output_hash": manifest["run"]["output_hash"],
        "rows_accepted": manifest["run"]["rows_accepted"],
    }
