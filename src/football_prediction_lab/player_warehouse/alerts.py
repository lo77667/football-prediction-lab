"""Operational coach-alert generation from the daily summary materialization."""

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


def build_high_risk_alerts(
    daily_summary: pd.DataFrame,
    *,
    alert_date: date | None = None,
    load_ratio_threshold: float = 1.50,
    confidence_threshold: float = -0.40,
) -> pd.DataFrame:
    """Return high-risk alert rows without writing to a database.

    The default pattern is a current physical load at least 1.5x the player's
    prior 28-observation average combined with a reviewed confidence score below
    -0.40. Missing baselines or missing psychological scores produce no alert;
    they should be shown as data-quality/review states rather than inferred risk.
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
    frame["load_ratio"] = frame["player_load_au"] / frame["prior_28_observation_load_avg"]
    eligible = frame.loc[
        frame["prior_28_observation_load_avg"].notna()
        & frame["player_load_au"].notna()
        & frame["confidence_score"].notna()
        & ~frame["qualitative_score_missing"].fillna(True)
        & (frame["load_ratio"] >= load_ratio_threshold)
        & (frame["confidence_score"] <= confidence_threshold)
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    eligible["alert_type"] = "high_load_low_confidence"
    eligible["severity"] = "high"
    eligible["alert_date"] = eligible["activity_date"]
    eligible["trigger_reason"] = eligible.apply(
        lambda row: (
            f"Player load is {row['load_ratio']:.2f}x prior 28-observation average "
            f"and confidence score is {row['confidence_score']:.2f}. Review workload, "
            "direct observation, and player check-in before changing the session."
        ),
        axis=1,
    )
    eligible["evidence"] = eligible.apply(
        lambda row: {
            "player_load_au": float(row["player_load_au"]),
            "prior_28_observation_load_avg": float(row["prior_28_observation_load_avg"]),
            "load_ratio": float(row["load_ratio"]),
            "confidence_score": float(row["confidence_score"]),
            "thresholds": {
                "load_ratio": load_ratio_threshold,
                "confidence_score": confidence_threshold,
            },
        },
        axis=1,
    )
    eligible["source_snapshot_date"] = eligible["activity_date"]
    eligible["dedupe_key"] = eligible.apply(
        lambda row: f"{row['player_id']}|{row['activity_date']}|high_load_low_confidence",
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
    """Scan the materialized view and idempotently insert new coach alerts.

    The function reads only the requested day, keeps the database transaction
    short, and uses ``dedupe_key`` to make retries safe. It assumes the migration
    has created ``analytics.mv_player_daily_summary`` and ``analytics.coach_alerts``.
    """

    select_sql = text(
        """
        SELECT player_id, activity_date, player_load_au,
               prior_28_observation_load_avg, confidence_score,
               qualitative_score_missing
        FROM analytics.mv_player_daily_summary
        WHERE activity_date = :alert_date
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
