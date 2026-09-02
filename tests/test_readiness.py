import pandas as pd
import pytest

from football_prediction_lab.evaluation.readiness import assess_commercial_readiness
from football_prediction_lab.evaluation.selection_provenance import SelectionProvenance


def frame(rows: int = 2, season: str = "2425") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": [f"m-{index}" for index in range(rows)],
            "season": [season] * rows,
        }
    )


def test_readiness_is_no_go_without_verified_source() -> None:
    result = assess_commercial_readiness(
        frame(100), source_verified=False, minimum_rows=100, edge_status="positive"
    )
    assert result.status == "no_go"
    assert result.ready_for_financial_execution is False
    assert "source_not_verified" in result.reasons


def provenance() -> SelectionProvenance:
    return SelectionProvenance(
        policy_id="policy-1",
        policy_sha256="a" * 64,
        snapshot_ids=["s-1"],
        snapshot_fingerprints=["b" * 64],
        market="btts",
        source_name="source-a",
        odds_type="pre_match",
    )


def test_readiness_requires_provenance() -> None:
    result = assess_commercial_readiness(
        frame(100), source_verified=True, minimum_rows=100, edge_status="positive"
    )
    assert result.status == "no_go"
    assert "selection_provenance_required" in result.reasons


def test_readiness_is_research_only_when_evidence_is_incomplete() -> None:
    result = assess_commercial_readiness(
        frame(10),
        source_verified=True,
        minimum_rows=100,
        edge_status="indeterminate",
        provenance=provenance(),
    )
    assert result.status == "research_only"
    assert set(result.reasons) == {
        "insufficient_match_rows",
        "edge_uncertainty_not_resolved",
    }


def test_readiness_conditional_is_not_financial_execution() -> None:
    result = assess_commercial_readiness(
        frame(100),
        source_verified=True,
        minimum_rows=100,
        edge_status="positive",
        provenance=provenance(),
    )
    assert result.status == "conditional"
    assert result.ready_for_financial_execution is False


def test_readiness_rejects_protected_holdout() -> None:
    with pytest.raises(ValueError, match="protected"):
        assess_commercial_readiness(frame(2, season="2526"), source_verified=True, minimum_rows=1)
