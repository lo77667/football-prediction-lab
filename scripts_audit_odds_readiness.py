"""Audit local odds availability without treating raw columns as snapshots."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from football_prediction_lab.data.provenance import build_manifest, sha256_file, write_manifest
from football_prediction_lab.evaluation.source_readiness import (
    select_manifested_source_files,
)

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
REPORT = ROOT / "reports" / "generated" / "cycle_32_odds_readiness.json"
SEASON_FILE = re.compile(r"^(?P<season>\d{4})_E0\.csv$")
ODDS_MARKERS = ("B365", "BW", "BF", "PS", "WH", "Avg", "Max", "AH", "OU")


def main() -> None:
    files = []
    odds_columns: set[str] = set()
    for path in sorted(RAW.glob("*_E0.csv")):
        match = SEASON_FILE.match(path.name)
        if match is None or match.group("season") == "2526":
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle))
        files.append(str(path.relative_to(ROOT)))
        odds_columns.update(
            column for column in header if any(marker in column for marker in ODDS_MARKERS)
        )

    source_selection = select_manifested_source_files(
        [ROOT / relative_path for relative_path in files]
    )
    report = {
        "cycle": 32,
        "source_name": "Football-Data.co.uk",
        "source_status": (
            "raw historical odds-like columns found; standardized snapshots unavailable"
        ),
        "real_odds_eligible": False,
        "economic_benchmark_status": "deferred_pending_licensed_timestamped_snapshots",
        "source_selection": source_selection,
        "raw_files_examined": len(files),
        "raw_files": files,
        "odds_like_columns_found": sorted(odds_columns),
        "standardized_snapshot_rows": 0,
        "discarded_rows": 0,
        "discarded_by_reason": {
            "missing_captured_at_per_quote": len(odds_columns),
            "missing_snapshot_provenance_and_input_sha256": len(odds_columns),
            "license_policy_not_attached_to_snapshot": len(odds_columns),
        },
        "coverage_by_season_market_source": {},
        "first_captured_at": None,
        "last_captured_at": None,
        "holdout_2526": {
            "excluded_from_source_selection": True,
            "excluded_from_benchmark": True,
            "excluded_from_tuning": True,
        },
        "financial_execution": False,
        "stake_sizing": False,
        "recommendation": False,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    raw_paths = [ROOT / path for path in files]
    digest_input = "".join(
        f"{path}:{sha256_file(path)};" for path in raw_paths
    )
    manifest = build_manifest(
        input_path=";".join(files),
        input_sha256=hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
        output_path=str(REPORT),
        rows_before=len(files),
        rows_after=0,
        frame=pd.DataFrame({"kickoff_utc": []}),
        feature_version="odds-readiness-v1",
    )
    write_manifest(
        manifest,
        REPORT.parent / "manifests" / "cycle_32_odds_readiness.manifest.json",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
