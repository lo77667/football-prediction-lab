"""Operational coach-alert generation with personalized adaptive thresholds."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

ALERT_COLUMNS = [
    "alert_type",
    "severity",
    "player_id",
    "alert_date",
    "trigger_reason",
    "evidence",
    "source_snapshot_date",
    "dedupe_key",
]

# These are transparent policy defaults, not clinical or medical thresholds. They
# should be versioned and approved by sports-science/safeguarding staff per academy.
AGE_BAND_MULTIPLIERS = {
    "U13": 0.90,
    "U14": 0.92,
    "U15": 0.95,
    "U16": 1.00,
    "U17": 1.03,
    "U18": 1.05,
    "U19": 1.05,
    "OTHER": 1.00,
}
SEASON_PHASE_MULTIPLIERS = {
    "pre_season": 1.10,
    "competition": 1.00,
    "taper": 0.95,
    "recovery": 0.90,
    "transition": 1.05,
    "OTHER": 1.00,
}


def _normalise_phase(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def adaptive_load_ratio_threshold(
    *,
    age_band: object = "OTHER",
    season_phase: object = "competition",
    base_threshold: float = 1.50,
    baseline_volatility_score: float | None = None,
) -> float:
    """Return a transparent player-specific load-ratio threshold.

    A younger age band tightens the default threshold, while pre-season and a
    volatile personal baseline loosen it modestly to reduce false positives. The
    result is clipped to 75%–135% of the base threshold so a single input cannot
    produce an extreme policy change.
    """

    if base_threshold <= 0:
        raise ValueError("base_threshold must be positive")
    volatility = 0.0 if baseline_volatility_score is None else float(baseline_volatility_score)
    if not 0 <= volatility <= 1:
        raise ValueError("baseline_volatility_score must be between 0 and 1")
    age_multiplier = AGE_BAND_MULTIPLIERS.get(str(age_band).upper(), 1.0)
    phase_multiplier = SEASON_PHASE_MULTIPLIERS.get(_normalise_phase(season_phase), 1.0)
    volatility_multiplier = 1.0 + 0.20 * volatility
    threshold = base_threshold * age_multiplier * phase_multiplier * volatility_multiplier
    return float(max(base_threshold * 0.75, min(base_threshold * 1.35, threshold)))


def build_high_risk_alerts(
    daily_summary: pd.DataFrame,
    *,
    alert_date: date | None = None,
    load_ratio_threshold: float = 1.50,
    confidence_threshold: float = -0.40,
) -> pd.DataFrame:
    """Return adaptive high-load/low-confidence alerts without database writes.

    The input may include ``age_band``, ``season_phase``, and
    ``baseline_volatility_score``. If an older caller omits them, safe defaults
    reproduce the original competition-phase threshold behavior.
    """

    required = {
        "player_id",
        "activity_date",
        "player_load_au",
        "prior_28_observation_load_avg",
        "confidence_score",
        "qualitative_score_missing",
    }
    missing = required - set(daily_summary.columns)
    if missing:
        raise ValueError(f"daily_summary is missing required columns: {sorted(missing)}")
    if load_ratio_threshold <= 0:
        raise ValueError("load_ratio_threshold must be positive")
    if not -1 <= confidence_threshold <= 0:
        raise ValueError("confidence_threshold must be between -1 and 0")

    frame = daily_summary.copy()
    frame["activity_date"] = pd.to_datetime(frame["activity_date"], utc=True).dt.date
    if alert_date is not None:
        frame = frame.loc[frame["activity_date"] == alert_date].copy()
    for column, default in (
        ("age_band", "OTHER"),
        ("season_phase", "competition"),
        ("baseline_volatility_score", 0.0),
    ):
        if column not in frame:
            frame[column] = default
        frame[column] = frame[column].fillna(default)
    frame["baseline_volatility_score"] = pd.to_numeric(
        frame["baseline_volatility_score"], errors="coerce"
    ).fillna(0.0).clip(0.0, 1.0)
    frame["load_ratio"] = frame["player_load_au"] / frame["prior_28_observation_load_avg"]
    frame["adaptive_threshold"] = frame.apply(
        lambda row: adaptive_load_ratio_threshold(
            age_band=row["age_band"],
            season_phase=row["season_phase"],
            base_threshold=load_ratio_threshold,
            baseline_volatility_score=row["baseline_volatility_score"],
        ),
        axis=1,
    )
    eligible = frame.loc[
        frame["prior_28_observation_load_avg"].notna()
        & frame["player_load_au"].notna()
        & frame["confidence_score"].notna()
        & ~frame["qualitative_score_missing"].fillna(True)
        & (frame["load_ratio"] >= frame["adaptive_threshold"])
        & (frame["confidence_score"] <= confidence_threshold)
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    eligible["alert_type"] = "adaptive_high_load_low_confidence"
    eligible["severity"] = "high"
    eligible["alert_date"] = eligible["activity_date"]
    eligible["trigger_reason"] = eligible.apply(
        lambda row: (
            f"Player load is {row['load_ratio']:.2f}x the prior 28-observation average; "
            f"adaptive threshold is {row['adaptive_threshold']:.2f} for {row['age_band']} "
            f"during {row['season_phase']}; confidence score is {row['confidence_score']:.2f}. "
            "Review workload, direct observation, and player check-in before changing the session."
        ),
        axis=1,
    )
    eligible["evidence"] = eligible.apply(
        lambda row: {
            "player_load_au": float(row["player_load_au"]),
            "prior_28_observation_load_avg": float(row["prior_28_observation_load_avg"]),
            "load_ratio": float(row["load_ratio"]),
            "adaptive_threshold": float(row["adaptive_threshold"]),
            "confidence_score": float(row["confidence_score"]),
            "age_band": str(row["age_band"]),
            "season_phase": str(row["season_phase"]),
            "baseline_volatility_score": float(row["baseline_volatility_score"]),
            "base_threshold": load_ratio_threshold,
            "confidence_threshold": confidence_threshold,
        },
        axis=1,
    )
    eligible["source_snapshot_date"] = eligible["activity_date"]
    eligible["dedupe_key"] = eligible.apply(
        lambda row: f"{row['player_id']}|{row['activity_date']}|adaptive_high_load_low_confidence",
        axis=1,
    )
    return eligible[ALERT_COLUMNS].reset_index(drop=True)


def scan_and_insert_coach_alerts(
    engine_or_connection: Engine | Connection,
    *,
    alert_date: date,
    load_ratio_threshold: float = 1.50,
    confidence_threshold: float = -0.40,
) -> int:
    """Scan one day and idempotently insert adaptive coach alerts.

    The phase calendar and volatility view are optional at the database level for
    compatibility with the original schema; missing matches fall back to the
    competition phase and zero volatility.
    """

    select_sql = text(
        """
        SELECT s.player_id, s.activity_date, s.player_load_au,
               s.prior_28_observation_load_avg, s.confidence_score,
               s.qualitative_score_missing, p.age_band,
               COALESCE(c.season_phase, 'competition') AS season_phase,
               COALESCE(v.baseline_volatility_score, 0.0) AS baseline_volatility_score
        FROM analytics.mv_player_daily_summary s
        JOIN core.player p ON p.player_id = s.player_id
        LEFT JOIN analytics.season_phase_calendar c
          ON s.activity_date BETWEEN c.start_date AND c.end_date
        LEFT JOIN analytics.v_player_load_baseline_volatility v
          ON v.player_id = s.player_id AND v.activity_date = s.activity_date
        WHERE s.activity_date = :alert_date
        """
    )
    insert_sql = text(
        """
        INSERT INTO analytics.coach_alerts (
            alert_type, severity, player_id, alert_date, trigger_reason,
            evidence, source_snapshot_date, dedupe_key
        ) VALUES (
            :alert_type, CAST(:severity AS analytics.alert_severity), :player_id,
            :alert_date, :trigger_reason, CAST(:evidence AS jsonb),
            :source_snapshot_date, :dedupe_key
        )
        ON CONFLICT (dedupe_key) DO NOTHING
        """
    )

    def execute(connection: Connection) -> int:
        summary = pd.read_sql_query(select_sql, connection, params={"alert_date": alert_date})
        alerts = build_high_risk_alerts(
            summary,
            alert_date=alert_date,
            load_ratio_threshold=load_ratio_threshold,
            confidence_threshold=confidence_threshold,
        )
        inserted = 0
        for row in alerts.to_dict(orient="records"):
            params: dict[str, Any] = {
                **row,
                "player_id": str(row["player_id"]),
                "alert_date": row["alert_date"],
                "source_snapshot_date": row["source_snapshot_date"],
                "evidence": json.dumps(row["evidence"], sort_keys=True),
            }
            result = connection.execute(insert_sql, params)
            inserted += int(result.rowcount == 1)
        return inserted

    if isinstance(engine_or_connection, Engine):
        with engine_or_connection.begin() as connection:
            return execute(connection)
    with engine_or_connection.begin():
        return execute(engine_or_connection)
