-- Personalized adaptive thresholds, longitudinal monitoring, and coach feedback
-- PostgreSQL 15+
-- Apply after 001_youth_player_warehouse.sql and 002_partitioned_summary_alerts.sql.

BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- -----------------------------------------------------------------------------
-- 1. Season phases used by adaptive alert policy
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analytics.season_phase_calendar (
  season_phase_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  season_code TEXT NOT NULL,
  season_phase TEXT NOT NULL CHECK (
    season_phase IN ('pre_season', 'competition', 'taper', 'recovery', 'transition', 'OTHER')
  ),
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_date >= start_date),
  UNIQUE (season_code, season_phase, start_date),
  EXCLUDE USING gist (daterange(start_date, end_date, '[]') WITH &&)
);

CREATE INDEX IF NOT EXISTS ix_season_phase_calendar_date
  ON analytics.season_phase_calendar (start_date, end_date, season_phase);

COMMENT ON TABLE analytics.season_phase_calendar IS
  'Academy-approved date ranges used to personalize non-clinical operational thresholds.';

-- -----------------------------------------------------------------------------
-- 2. Player-specific baseline volatility
-- -----------------------------------------------------------------------------
-- Coefficient of variation over the prior 28 observed daily load rows. It is
-- clipped to [0, 1] so it can be used as a bounded sensitivity adjustment.

CREATE OR REPLACE VIEW analytics.v_player_load_baseline_volatility AS
WITH daily_load AS (
  SELECT
    player_id,
    activity_date,
    player_load_au,
    AVG(player_load_au) OVER (
      PARTITION BY player_id
      ORDER BY activity_date
      ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
    ) AS prior_28_load_mean,
    STDDEV_SAMP(player_load_au) OVER (
      PARTITION BY player_id
      ORDER BY activity_date
      ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
    ) AS prior_28_load_stddev,
    COUNT(player_load_au) OVER (
      PARTITION BY player_id
      ORDER BY activity_date
      ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
    ) AS prior_28_load_n
  FROM facts.player_load_daily
  WHERE quality_status = 'accepted'
)
SELECT
  player_id,
  activity_date,
  prior_28_load_n,
  prior_28_load_mean,
  prior_28_load_stddev,
  CASE
    WHEN prior_28_load_n < 7 OR prior_28_load_mean IS NULL OR prior_28_load_mean = 0 THEN NULL
    ELSE LEAST(
      1.0,
      GREATEST(0.0, prior_28_load_stddev / NULLIF(prior_28_load_mean, 0))
    )
  END AS baseline_volatility_score
FROM daily_load;

COMMENT ON VIEW analytics.v_player_load_baseline_volatility IS
  'Bounded coefficient-of-variation score from prior daily load; NULL until seven observations exist.';

-- -----------------------------------------------------------------------------
-- 3. Longitudinal development trajectory
-- -----------------------------------------------------------------------------
-- Slopes are expressed as change per 30 days. The view returns the latest
-- available daily summary per player and a trailing-window regression slope.
-- Resilience is a developmental recovery signal, not a mental-health assessment.

CREATE OR REPLACE VIEW analytics.v_player_development_trajectory AS
WITH latest AS (
  SELECT DISTINCT ON (player_id)
    player_id,
    activity_date AS latest_activity_date
  FROM analytics.mv_player_daily_summary
  ORDER BY player_id, activity_date DESC
),
series AS (
  SELECT
    s.*,
    l.latest_activity_date,
    EXTRACT(EPOCH FROM s.activity_date::timestamp) AS activity_epoch,
    s.progressive_actions / NULLIF(s.minutes_played, 0) * 90.0 AS progressive_actions_per_90,
    s.key_passes / NULLIF(s.minutes_played, 0) * 90.0 AS key_passes_per_90,
    s.player_load_au / NULLIF(s.prior_28_observation_load_avg, 0) AS load_ratio
  FROM analytics.mv_player_daily_summary s
  JOIN latest l USING (player_id)
),
slopes AS (
  SELECT
    player_id,
    latest_activity_date,
    MAX(age_band) AS age_band,
    MAX(primary_position) AS primary_position,
    MAX(activity_date) AS last_observed_date,
    MAX(analyst_rating) FILTER (
      WHERE activity_date = latest_activity_date
    ) AS latest_analyst_rating,
    MAX(confidence_score) FILTER (
      WHERE activity_date = latest_activity_date
    ) AS latest_confidence_score,
    MAX(readiness_score) FILTER (
      WHERE activity_date = latest_activity_date
    ) AS latest_readiness_score,
    regr_slope(analyst_rating, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '6 months'
    ) * 30.0 * 86400.0 AS analyst_rating_slope_6m_per_30d,
    regr_slope(analyst_rating, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '12 months'
    ) * 30.0 * 86400.0 AS analyst_rating_slope_12m_per_30d,
    regr_slope(progressive_actions_per_90, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '6 months'
    ) * 30.0 * 86400.0 AS progressive_actions_slope_6m_per_30d,
    regr_slope(progressive_actions_per_90, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '12 months'
    ) * 30.0 * 86400.0 AS progressive_actions_slope_12m_per_30d,
    regr_slope(key_passes_per_90, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '6 months'
    ) * 30.0 * 86400.0 AS key_passes_slope_6m_per_30d,
    regr_slope(key_passes_per_90, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '12 months'
    ) * 30.0 * 86400.0 AS key_passes_slope_12m_per_30d,
    regr_slope(confidence_score, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '6 months'
    ) * 30.0 * 86400.0 AS confidence_slope_6m_per_30d,
    regr_slope(confidence_score, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '12 months'
    ) * 30.0 * 86400.0 AS confidence_slope_12m_per_30d,
    regr_slope(readiness_score, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '6 months'
    ) * 30.0 * 86400.0 AS readiness_slope_6m_per_30d,
    regr_slope(readiness_score, activity_epoch) FILTER (
      WHERE activity_date > latest_activity_date - INTERVAL '12 months'
    ) * 30.0 * 86400.0 AS readiness_slope_12m_per_30d
  FROM series
  GROUP BY player_id, latest_activity_date
),
events AS (
  SELECT
    player_id,
    activity_date AS event_date,
    load_ratio,
    confidence_score,
    CASE
      WHEN load_ratio >= 1.50 OR confidence_score <= -0.40 THEN TRUE
      ELSE FALSE
    END AS is_stress_event
  FROM series
),
recovery AS (
  SELECT
    e.player_id,
    e.event_date,
    MIN(s.activity_date) AS recovery_date
  FROM events e
  JOIN series s
    ON s.player_id = e.player_id
   AND s.activity_date > e.event_date
   AND s.activity_date <= e.event_date + INTERVAL '30 days'
   AND (
     s.load_ratio IS NULL OR s.load_ratio <= 1.20
   )
   AND (
     s.confidence_score IS NULL OR s.confidence_score >= -0.20
   )
  WHERE e.is_stress_event
  GROUP BY e.player_id, e.event_date
),
resilience AS (
  SELECT
    player_id,
    COUNT(*) AS stress_event_count,
    COUNT(recovery_date) AS recovered_event_count,
    AVG(EXTRACT(EPOCH FROM (recovery_date - event_date)) / 86400.0)
      FILTER (WHERE recovery_date IS NOT NULL) AS mean_recovery_days,
    CASE
      WHEN COUNT(*) < 2 OR COUNT(recovery_date) = 0 THEN NULL
      ELSE LEAST(
        1.0,
        GREATEST(
          0.0,
          (COUNT(recovery_date)::numeric / COUNT(*)::numeric)
          * (1.0 / (1.0 + AVG(EXTRACT(EPOCH FROM (recovery_date - event_date)) / 86400.0)
            FILTER (WHERE recovery_date IS NOT NULL) / 14.0))
        )
      )
    END AS resilience_score
  FROM recovery
  GROUP BY player_id
)
SELECT
  s.*,
  r.stress_event_count,
  r.recovered_event_count,
  r.mean_recovery_days,
  r.resilience_score
FROM slopes s
LEFT JOIN resilience r USING (player_id);

COMMENT ON VIEW analytics.v_player_development_trajectory IS
  'Trailing 6/12-month per-30-day slopes and event-recovery resilience; requires human interpretation.';

CREATE INDEX IF NOT EXISTS ix_mv_daily_summary_player_activity
  ON analytics.mv_player_daily_summary (player_id, activity_date DESC);

-- -----------------------------------------------------------------------------
-- 4. Coach feedback log
-- -----------------------------------------------------------------------------

CREATE TYPE analytics.coach_feedback_rating AS ENUM ('very_inaccurate', 'inaccurate', 'uncertain', 'accurate', 'very_accurate');
CREATE TYPE analytics.coach_observed_action AS ENUM ('followed', 'modified', 'overrode', 'not_applicable');

CREATE TABLE analytics.coach_feedback_log (
  feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prediction_id UUID REFERENCES analytics.model_prediction(prediction_id),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  recommendation_date DATE NOT NULL,
  recommended_decision TEXT NOT NULL CHECK (recommended_decision IN ('GO', 'NO-GO', 'REVIEW')),
  coach_observed_action analytics.coach_observed_action NOT NULL,
  accuracy_rating analytics.coach_feedback_rating NOT NULL,
  outcome_window_end_date DATE,
  observed_outcome NUMERIC(12, 6),
  feedback_reason TEXT CHECK (feedback_reason IS NULL OR length(feedback_reason) <= 1000),
  logged_by_role TEXT NOT NULL CHECK (
    logged_by_role IN ('coach', 'analyst', 'sports_scientist', 'safeguarding')
  ),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (outcome_window_end_date IS NULL OR outcome_window_end_date >= recommendation_date)
);

CREATE INDEX ix_coach_feedback_player_date
  ON analytics.coach_feedback_log (player_id, recommendation_date DESC);
CREATE INDEX ix_coach_feedback_prediction
  ON analytics.coach_feedback_log (prediction_id);
CREATE INDEX ix_coach_feedback_rating
  ON analytics.coach_feedback_log (accuracy_rating, recommendation_date DESC);

COMMENT ON TABLE analytics.coach_feedback_log IS
  'Role-restricted human feedback used for monitoring and future model evaluation; not an automatic label.';

COMMIT;
