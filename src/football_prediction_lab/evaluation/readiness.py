"""Fail-closed readiness decisions for commercial evaluation."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from football_prediction_lab.evaluation.commercial_report import (
    assert_no_protected_holdout,
)


class ReadinessDecision(BaseModel):
    """Explicit status; conditional never means profitable or ready to bet."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["no_go", "research_only", "conditional"]
    ready_for_financial_execution: bool = False
    rows: int = Field(ge=0)
    reasons: list[str]


def assess_commercial_readiness(
    frame: pd.DataFrame,
    *,
    source_verified: bool,
    minimum_rows: int = 100,
    protected_seasons: set[str] | None = None,
    edge_status: str | None = None,
) -> ReadinessDecision:
    """Return a no-go or research-only decision unless all evidence gates pass."""

    if minimum_rows < 1:
        raise ValueError("minimum_rows must be positive")
    assert_no_protected_holdout(frame, protected_seasons=protected_seasons)
    reasons: list[str] = []
    if not source_verified:
        reasons.append("source_not_verified")
    if len(frame) < minimum_rows:
        reasons.append("insufficient_match_rows")
    if edge_status in {"indeterminate", "unavailable"}:
        reasons.append("edge_uncertainty_not_resolved")
    if reasons:
        status = "no_go" if "source_not_verified" in reasons else "research_only"
        return ReadinessDecision(status=status, rows=len(frame), reasons=reasons)
    return ReadinessDecision(
        status="conditional",
        rows=len(frame),
        reasons=["descriptive_evidence_only"],
    )
