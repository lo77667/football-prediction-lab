-- Youth Player Hybrid Warehouse operational enhancement
-- PostgreSQL 15+
-- One-time cutover migration for an already-created 001_youth_player_warehouse.sql.
-- Review the year range and retention policy before production execution.

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Range partitioning by activity_date
-- -----------------------------------------------------------------------------
-- player_match_performance did not previously contain a date key. We derive it
-- from core.match.kickoff_utc and carry season_code for pruning/reporting.
-- The legacy tables are retained until row counts and application smoke tests
-- are verified. They can be dropped in a later, separately approved migration.

LOCK TABLE facts.player_match_performance IN ACCESS EXCLUSIVE MODE;
ALTER TABLE facts.player_match_performance RENAME TO player_match_performance_legacy;

CREATE TABLE facts.player_match_performance (
  player_match_id UUID NOT NULL,
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  match_id UUID NOT NULL REFERENCES core.match(match_id),
  minutes_played NUMERIC(5, 2) NOT NULL CHECK (minutes_played BETWEEN 0 AND 150),
  started BOOLEAN NOT NULL DEFAULT FALSE,
  position core.position_code NOT NULL DEFAULT 'UNKNOWN',
  goals NUMERIC(5, 2) NOT NULL DEFAULT 0 CHECK (goals >= 0),
  assists NUMERIC(5, 2) NOT NULL DEFAULT 0 CHECK (assists >= 0),
  shots NUMERIC(6, 2) NOT NULL DEFAULT 0 CHECK (shots >= 0),
  key_passes NUMERIC(6, 2) NOT NULL DEFAULT 0 CHECK (key_passes >= 0),
  progressive_actions NUMERIC(7, 2) NOT NULL DEFAULT 0 CHECK (progressive_actions >= 0),
  duels_won NUMERIC(6, 2) NOT NULL DEFAULT 0 CHECK (duels_won >= 0),
  turnovers NUMERIC(6, 2) NOT NULL DEFAULT 0 CHECK (turnovers >= 0),
  recoveries NUMERIC(6, 2) NOT NULL DEFAULT 0 CHECK (recoveries >= 0),
  high_intensity_actions NUMERIC(7, 2) CHECK (high_intensity_actions >= 0),
  analyst_rating NUMERIC(5, 4) CHECK (analyst_rating BETWEEN 0 AND 1),
  observed_at_utc TIMESTAMPTZ NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  quality_status facts.quality_status NOT NULL DEFAULT 'accepted',
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  activity_date DATE NOT NULL,
  season_code TEXT NOT NULL DEFAULT 'unknown',
  CHECK (available_at_utc >= observed_at_utc),
  CONSTRAINT uq_player_match_performance_partitioned_id UNIQUE (player_match_id, activity_date),
  CONSTRAINT uq_player_match_performance_partitioned_player_match UNIQUE (player_id, match_id, activity_date),
  CONSTRAINT uq_player_match_performance_partitioned_source UNIQUE (source_system, source_record_id, activity_date)
) PARTITION BY RANGE (activity_date);

DO $$
DECLARE
  year_value INTEGER;
BEGIN
  FOR year_value IN 2015..2035 LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS facts.player_match_performance_y%s PARTITION OF facts.player_match_performance FOR VALUES FROM (%L) TO (%L)',
      year_value,
      make_date(year_value, 1, 1),
      make_date(year_value + 1, 1, 1)
    );
  END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS facts.player_match_performance_default
  PARTITION OF facts.player_match_performance DEFAULT;

INSERT INTO facts.player_match_performance (
  player_match_id, player_id, match_id, minutes_played, started, position,
  goals, assists, shots, key_passes, progressive_actions, duels_won, turnovers,
  recoveries, high_intensity_actions, analyst_rating, observed_at_utc,
  available_at_utc, quality_status, source_system, source_record_id,
  activity_date, season_code
)
SELECT
  p.player_match_id, p.player_id, p.match_id, p.minutes_played, p.started, p.position,
  p.goals, p.assists, p.shots, p.key_passes, p.progressive_actions, p.duels_won,
  p.turnovers, p.recoveries, p.high_intensity_actions, p.analyst_rating,
  p.observed_at_utc, p.available_at_utc, p.quality_status, p.source_system,
  p.source_record_id, m.kickoff_utc::date, COALESCE(t.season_code, 'unknown')
FROM facts.player_match_performance_legacy p
JOIN core.match m ON m.match_id = p.match_id
LEFT JOIN core.academy_team t ON t.team_id = m.team_id;

CREATE INDEX ix_performance_partition_player_date
  ON facts.player_match_performance (player_id, activity_date DESC);
CREATE INDEX ix_performance_partition_match_date
  ON facts.player_match_performance (match_id, activity_date);
CREATE INDEX ix_performance_partition_source
  ON facts.player_match_performance (source_system, source_record_id, activity_date);

LOCK TABLE facts.player_load_daily IN ACCESS EXCLUSIVE MODE;
ALTER TABLE facts.player_load_daily RENAME TO player_load_daily_legacy;

CREATE TABLE facts.player_load_daily (
  load_id UUID NOT NULL DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  activity_date DATE NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  session_count INTEGER NOT NULL DEFAULT 0 CHECK (session_count >= 0),
  duration_min NUMERIC(7, 2) CHECK (duration_min >= 0),
  total_distance_m NUMERIC(10, 2) CHECK (total_distance_m >= 0),
  high_speed_distance_m NUMERIC(10, 2) CHECK (high_speed_distance_m >= 0),
  sprint_distance_m NUMERIC(10, 2) CHECK (sprint_distance_m >= 0),
  accelerations INTEGER CHECK (accelerations >= 0),
  decelerations INTEGER CHECK (decelerations >= 0),
  player_load_au NUMERIC(10, 2) CHECK (player_load_au >= 0),
  data_completeness_pct NUMERIC(5, 2) CHECK (data_completeness_pct BETWEEN 0 AND 100),
  quality_status facts.quality_status NOT NULL DEFAULT 'accepted',
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  CONSTRAINT uq_player_load_daily_partitioned_id UNIQUE (load_id, activity_date),
  CONSTRAINT uq_player_load_daily_partitioned_player_date UNIQUE (player_id, activity_date),
  CONSTRAINT uq_player_load_daily_partitioned_source UNIQUE (source_system, source_record_id, activity_date)
) PARTITION BY RANGE (activity_date);

DO $$
DECLARE
  year_value INTEGER;
BEGIN
  FOR year_value IN 2015..2035 LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS facts.player_load_daily_y%s PARTITION OF facts.player_load_daily FOR VALUES FROM (%L) TO (%L)',
      year_value,
      make_date(year_value, 1, 1),
      make_date(year_value + 1, 1, 1)
    );
  END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS facts.player_load_daily_default
  PARTITION OF facts.player_load_daily DEFAULT;

INSERT INTO facts.player_load_daily (
  load_id, player_id, activity_date, available_at_utc, session_count,
  duration_min, total_distance_m, high_speed_distance_m, sprint_distance_m,
  accelerations, decelerations, player_load_au, data_completeness_pct,
  quality_status, source_system, source_record_id
)
SELECT
  load_id, player_id, activity_date, available_at_utc, session_count,
  duration_min, total_distance_m, high_speed_distance_m, sprint_distance_m,
  accelerations, decelerations, player_load_au, data_completeness_pct,
  quality_status, source_system, source_record_id
FROM facts.player_load_daily_legacy;

CREATE INDEX ix_load_partition_player_date
  ON facts.player_load_daily (player_id, activity_date DESC);
CREATE INDEX ix_load_partition_quality_date
  ON facts.player_load_daily (quality_status, activity_date);

ANALYZE facts.player_match_performance;
ANALYZE facts.player_load_daily;

-- -----------------------------------------------------------------------------
-- 2. Materialized view for dashboard reads
-- -----------------------------------------------------------------------------
-- The view is one row per player/date. Qualitative values are latest eligible
-- reviewed feature values available by the UTC end of that date. The rolling
-- load baseline is based on the prior 28 observed daily rows and deliberately
-- excludes the current day to avoid alert leakage.

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_player_daily_summary;

CREATE MATERIALIZED VIEW analytics.mv_player_daily_summary AS
WITH performance_by_day AS (
  SELECT
    player_id,
    activity_date,
    SUM(minutes_played) AS minutes_played,
    SUM(goals) AS goals,
    SUM(assists) AS assists,
    SUM(shots) AS shots,
    SUM(key_passes) AS key_passes,
    SUM(progressive_actions) AS progressive_actions,
    SUM(duels_won) AS duels_won,
    SUM(turnovers) AS turnovers,
    SUM(recoveries) AS recoveries,
    AVG(analyst_rating) AS analyst_rating,
    COUNT(*) AS match_count
  FROM facts.player_match_performance
  WHERE quality_status = 'accepted'
  GROUP BY player_id, activity_date
),
load_by_day_raw AS (
  SELECT
    player_id,
    activity_date,
    SUM(duration_min) AS duration_min,
    SUM(total_distance_m) AS total_distance_m,
    SUM(high_speed_distance_m) AS high_speed_distance_m,
    SUM(sprint_distance_m) AS sprint_distance_m,
    SUM(accelerations) AS accelerations,
    SUM(decelerations) AS decelerations,
    SUM(player_load_au) AS player_load_au,
    AVG(data_completeness_pct) AS load_completeness_pct
  FROM facts.player_load_daily
  WHERE quality_status = 'accepted'
  GROUP BY player_id, activity_date
),
load_by_day AS (
  SELECT
    r.*,
    AVG(player_load_au) OVER (
      PARTITION BY player_id
      ORDER BY activity_date
      ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
    ) AS prior_28_observation_load_avg
  FROM load_by_day_raw r
),
all_player_days AS (
  SELECT player_id, activity_date FROM performance_by_day
  UNION
  SELECT player_id, activity_date FROM load_by_day
),
latest_qualitative AS (
  SELECT
    d.player_id,
    d.activity_date,
    q.qualitative_scores,
    (q.qualitative_scores ->> 'confidence')::numeric AS confidence_score,
    (q.qualitative_scores ->> 'readiness')::numeric AS readiness_score
  FROM all_player_days d
  LEFT JOIN LATERAL (
    SELECT
      jsonb_object_agg(x.feature_name, x.feature_value ORDER BY x.feature_name) AS qualitative_scores
    FROM (
      SELECT DISTINCT ON (feature_name)
        feature_name,
        feature_value
      FROM analytics.qualitative_feature_daily
      WHERE player_id = d.player_id
        AND feature_date <= d.activity_date
        AND as_of_utc < ((d.activity_date + 1)::timestamp AT TIME ZONE 'UTC')
        AND feature_value IS NOT NULL
        AND review_status IN ('coach_reviewed', 'sports_science_reviewed')
      ORDER BY feature_name, feature_date DESC, as_of_utc DESC
    ) x
  ) q ON TRUE
)
SELECT
  d.player_id,
  d.activity_date,
  p.age_band,
  p.primary_position,
  COALESCE(perf.minutes_played, 0) AS minutes_played,
  COALESCE(perf.goals, 0) AS goals,
  COALESCE(perf.assists, 0) AS assists,
  COALESCE(perf.shots, 0) AS shots,
  COALESCE(perf.key_passes, 0) AS key_passes,
  COALESCE(perf.progressive_actions, 0) AS progressive_actions,
  COALESCE(perf.duels_won, 0) AS duels_won,
  COALESCE(perf.turnovers, 0) AS turnovers,
  COALESCE(perf.recoveries, 0) AS recoveries,
  perf.analyst_rating,
  COALESCE(perf.match_count, 0) AS match_count,
  load.duration_min,
  load.total_distance_m,
  load.high_speed_distance_m,
  load.sprint_distance_m,
  load.accelerations,
  load.decelerations,
  load.player_load_au,
  load.load_completeness_pct,
  load.prior_28_observation_load_avg,
  qual.qualitative_scores,
  qual.confidence_score,
  qual.readiness_score,
  (qual.confidence_score IS NULL) AS qualitative_score_missing,
  now() AS refreshed_at_utc
FROM all_player_days d
JOIN core.player p ON p.player_id = d.player_id
LEFT JOIN performance_by_day perf USING (player_id, activity_date)
LEFT JOIN load_by_day load USING (player_id, activity_date)
LEFT JOIN latest_qualitative qual USING (player_id, activity_date);

CREATE UNIQUE INDEX ux_mv_player_daily_summary
  ON analytics.mv_player_daily_summary (player_id, activity_date);
CREATE INDEX ix_mv_player_daily_summary_date
  ON analytics.mv_player_daily_summary (activity_date, player_id);
CREATE INDEX ix_mv_player_daily_summary_alert_scan
  ON analytics.mv_player_daily_summary (activity_date, player_load_au, confidence_score);

-- Refresh from an external scheduler after all daily loads and reviewed
-- qualitative features have landed:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_player_daily_summary;
-- The unique index above is required for CONCURRENTLY. Schedule once per day
-- after ingestion, and run ANALYZE after unusually large backfills. For very
-- large history, replace this full refresh with an incremental summary table.

-- -----------------------------------------------------------------------------
-- 3. Coach alerts
-- -----------------------------------------------------------------------------

CREATE TYPE analytics.alert_severity AS ENUM ('info', 'warning', 'high', 'critical');
CREATE TYPE analytics.alert_acknowledgment_status AS ENUM (
  'unacknowledged', 'acknowledged', 'snoozed', 'resolved', 'dismissed'
);

CREATE TABLE analytics.coach_alerts (
  alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_type TEXT NOT NULL,
  severity analytics.alert_severity NOT NULL,
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  alert_date DATE NOT NULL,
  trigger_reason TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_snapshot_date DATE,
  acknowledgment_status analytics.alert_acknowledgment_status NOT NULL DEFAULT 'unacknowledged',
  acknowledged_by TEXT,
  acknowledged_at_utc TIMESTAMPTZ,
  resolved_at_utc TIMESTAMPTZ,
  resolution_note TEXT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  dedupe_key TEXT NOT NULL UNIQUE,
  CHECK (acknowledged_at_utc IS NULL OR acknowledgment_status <> 'unacknowledged'),
  CHECK (resolved_at_utc IS NULL OR acknowledgment_status IN ('resolved', 'dismissed'))
);

CREATE INDEX ix_coach_alerts_open
  ON analytics.coach_alerts (severity, alert_date DESC)
  WHERE acknowledgment_status IN ('unacknowledged', 'acknowledged', 'snoozed');
CREATE INDEX ix_coach_alerts_player_date
  ON analytics.coach_alerts (player_id, alert_date DESC);

COMMIT;
