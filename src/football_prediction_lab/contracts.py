"""Stable data contracts shared by ingestion, modeling, and evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Market = Literal["btts", "total_yellows_over_3_5"]



class MatchRecord(BaseModel):
    """A normalized football match record."""

    model_config = ConfigDict(extra="forbid")

    match_id: str = Field(min_length=1)
    kickoff_utc: datetime
    competition: str = Field(min_length=1)
    season: str = Field(min_length=1)
    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)
    source: str = Field(min_length=1)

    @field_validator("home_team", "away_team")
    @classmethod
    def strip_team_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("team name cannot be blank")
        return value


class PredictionRecord(BaseModel):
    """A prediction written before the result is revealed."""

    model_config = ConfigDict(extra="forbid")

    prediction_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    market: Market
    predicted_at_utc: datetime
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    probability_yes: float = Field(ge=0.0, le=1.0)
    decision: Literal["yes", "no", "no_signal"]
    data_cutoff_utc: datetime
    input_fingerprint: str = Field(min_length=1)


class OutcomeRecord(BaseModel):
    """Outcome revealed after a prediction has been permanently recorded."""

    model_config = ConfigDict(extra="forbid")

    prediction_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    market: Market
    revealed_at_utc: datetime
    actual_yes: bool
    result_source: str = Field(min_length=1)


class EvaluationRecord(BaseModel):
    """Point-in-time evaluation linking a prediction to a later outcome."""

    model_config = ConfigDict(extra="forbid")

    prediction_id: str = Field(min_length=1)
    market: Market
    probability_yes: float = Field(ge=0.0, le=1.0)
    actual_yes: bool
    brier_score: float = Field(ge=0.0, le=1.0)
    correct_decision: bool
    model_version: str = Field(min_length=1)
