from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "quality" / "scripts_audit_odds_readiness.py"
_SPEC = spec_from_file_location("scripts_audit_odds_readiness", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_READINESS = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_READINESS)
validate_snapshot_count_invariants = _READINESS.validate_snapshot_count_invariants


def report(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "raw_snapshot_rows": 0,
        "standardized_snapshot_rows": 0,
        "discarded_snapshot_rows": 0,
        "snapshot_rejections_by_reason": {},
        "odds_like_columns_count": 94,
        "source_observations": {
            "odds_like_columns_found": ["B365H"],
            "rejected_source_files": [],
            "source_rejections_by_reason": {"missing_manifest": 10},
        },
    }
    value.update(overrides)
    return value


def test_empty_snapshots_keep_source_findings_out_of_row_counts() -> None:
    value = report()

    validate_snapshot_count_invariants(value)

    assert value["raw_snapshot_rows"] == 0
    assert value["standardized_snapshot_rows"] == 0
    assert value["discarded_snapshot_rows"] == 0
    assert value["snapshot_rejections_by_reason"] == {}
    assert value["source_observations"]["source_rejections_by_reason"] == {"missing_manifest": 10}


def test_snapshot_rejections_sum_to_discarded_rows() -> None:
    value = report(
        raw_snapshot_rows=5,
        standardized_snapshot_rows=3,
        discarded_snapshot_rows=2,
        snapshot_rejections_by_reason={"missing_captured_at": 1, "invalid_odds": 1},
    )

    validate_snapshot_count_invariants(value)


def test_rejects_mismatched_snapshot_rejection_sum() -> None:
    value = report(
        raw_snapshot_rows=5,
        standardized_snapshot_rows=3,
        discarded_snapshot_rows=2,
        snapshot_rejections_by_reason={"missing_captured_at": 1},
    )

    with pytest.raises(ValueError, match="must equal snapshot rejection counts"):
        validate_snapshot_count_invariants(value)


def test_rejects_snapshot_counts_above_raw_rows() -> None:
    value = report(
        raw_snapshot_rows=1,
        standardized_snapshot_rows=1,
        discarded_snapshot_rows=1,
        snapshot_rejections_by_reason={"invalid_odds": 1},
    )

    with pytest.raises(ValueError, match="cannot exceed raw rows"):
        validate_snapshot_count_invariants(value)


def test_rejects_nonzero_counts_when_no_snapshots_exist() -> None:
    value = report(standardized_snapshot_rows=1)

    with pytest.raises(ValueError, match="empty snapshot input"):
        validate_snapshot_count_invariants(value)
