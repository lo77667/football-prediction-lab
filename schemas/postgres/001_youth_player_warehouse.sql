-- Youth Player Hybrid Analytics Warehouse
-- PostgreSQL 15+
-- No direct identifiers belong in this schema. Identity mapping lives in a separately
-- permissioned service/vault. All timestamps are stored as timestamptz in UTC.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS facts;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TYPE core.position_code AS ENUM (
  'GK', 'CB', 'FB', 'WB', 'DM', 'CM', 'AM', 'W', 'ST', 'FLEX', 'UNKNOWN'
);

CREATE TYPE governance.consent_purpose AS ENUM (
  'performance_development', 'sports_science', 'wellness', 'research', 'safeguarding'
);

CREATE TYPE governance.consent_status AS ENUM (
  'pending', 'active', 'withdrawn', 'expired', 'superseded'
);

CREATE TYPE facts.quality_status AS ENUM (
  'accepted', 'suspect', 'quarantined', 'corrected'
);

CREATE TYPE analytics.review_status AS ENUM (
  'not_reviewed', 'coach_reviewed', 'sports_science_reviewed', 'safeguarding_restricted', 'rejected'
);

CREATE TABLE core.player (
  player_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_code TEXT NOT NULL UNIQUE,
  age_band TEXT NOT NULL CHECK (age_band IN ('U13', 'U14', 'U15', 'U16', 'U17', 'U18', 'U19', 'OTHER')),
  primary_position core.position_code NOT NULL DEFAULT 'UNKNOWN',
  dominant_foot TEXT CHECK (dominant_foot IN ('left', 'right', 'both', 'unknown')),
  cohort_code TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.player IS 'Pseudonymous player dimension; no name, email, phone, date of birth, or contact fields.';
COMMENT ON COLUMN core.player.player_code IS 'Non-semantic display code. Never derive it from name or date of birth.';

CREATE TABLE core.academy_team (
  team_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_code TEXT NOT NULL UNIQUE,
  team_name TEXT NOT NULL,
  season_code TEXT NOT NULL,
  age_band TEXT NOT NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.player_team_membership (
  membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  team_id UUID NOT NULL REFERENCES core.academy_team(team_id),
  valid_during TSTZRANGE NOT NULL,
  source_system TEXT NOT NULL,
  recorded_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  EXCLUDE USING gist (player_id WITH =, valid_during WITH &&)
);

CREATE TABLE core.match (
  match_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID REFERENCES core.academy_team(team_id),
  kickoff_utc TIMESTAMPTZ NOT NULL,
  competition_code TEXT NOT NULL,
  opponent_code TEXT,
  venue TEXT CHECK (venue IN ('home', 'away', 'neutral', 'unknown')),
  surface TEXT,
  match_importance NUMERIC(5, 4) CHECK (match_importance BETWEEN 0 AND 1),
  source_system TEXT NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (available_at_utc >= kickoff_utc)
);

CREATE INDEX ix_match_kickoff ON core.match (kickoff_utc, match_id);

CREATE TABLE facts.player_match_performance (
  player_match_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  UNIQUE (player_id, match_id),
  UNIQUE (source_system, source_record_id),
  CHECK (available_at_utc >= observed_at_utc)
);

CREATE INDEX ix_performance_player_match ON facts.player_match_performance (player_id, match_id);

CREATE TABLE facts.physical_assessment (
  assessment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  assessment_at_utc TIMESTAMPTZ NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  height_cm NUMERIC(6, 2) CHECK (height_cm BETWEEN 100 AND 230),
  mass_kg NUMERIC(6, 2) CHECK (mass_kg BETWEEN 20 AND 150),
  sprint_10m_s NUMERIC(6, 3) CHECK (sprint_10m_s BETWEEN 1 AND 10),
  sprint_30m_s NUMERIC(6, 3) CHECK (sprint_30m_s BETWEEN 3 AND 20),
  jump_cm NUMERIC(6, 2) CHECK (jump_cm BETWEEN 0 AND 100),
  agility_505_s NUMERIC(6, 3) CHECK (agility_505_s BETWEEN 1 AND 15),
  aerobic_distance_m NUMERIC(8, 2) CHECK (aerobic_distance_m >= 0),
  asymmetry_pct NUMERIC(5, 2) CHECK (asymmetry_pct BETWEEN 0 AND 100),
  measurement_protocol TEXT NOT NULL,
  assessor_role TEXT NOT NULL,
  quality_status facts.quality_status NOT NULL DEFAULT 'accepted',
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  UNIQUE (player_id, assessment_at_utc, measurement_protocol),
  UNIQUE (source_system, source_record_id),
  CHECK (available_at_utc >= assessment_at_utc)
);

CREATE INDEX ix_physical_player_time ON facts.physical_assessment (player_id, assessment_at_utc DESC);

CREATE TABLE facts.player_load_daily (
  load_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  UNIQUE (player_id, activity_date),
  UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_load_player_date ON facts.player_load_daily (player_id, activity_date DESC);

CREATE TABLE facts.wellness_daily (
  wellness_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  activity_date DATE NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  sleep_quality NUMERIC(5, 4) CHECK (sleep_quality BETWEEN 0 AND 1),
  soreness NUMERIC(5, 4) CHECK (soreness BETWEEN 0 AND 1),
  stress NUMERIC(5, 4) CHECK (stress BETWEEN 0 AND 1),
  mood NUMERIC(5, 4) CHECK (mood BETWEEN 0 AND 1),
  energy NUMERIC(5, 4) CHECK (energy BETWEEN 0 AND 1),
  completion_status TEXT NOT NULL DEFAULT 'complete',
  consent_purpose governance.consent_purpose NOT NULL DEFAULT 'wellness',
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  UNIQUE (player_id, activity_date),
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE governance.consent_record (
  consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  purpose governance.consent_purpose NOT NULL,
  status governance.consent_status NOT NULL,
  policy_version TEXT NOT NULL,
  jurisdiction_code TEXT NOT NULL,
  assent_recorded BOOLEAN NOT NULL DEFAULT FALSE,
  parental_authorization_recorded BOOLEAN NOT NULL DEFAULT FALSE,
  granted_at_utc TIMESTAMPTZ,
  expires_at_utc TIMESTAMPTZ,
  withdrawn_at_utc TIMESTAMPTZ,
  source_receipt_id TEXT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (expires_at_utc IS NULL OR granted_at_utc IS NULL OR expires_at_utc > granted_at_utc),
  CHECK (withdrawn_at_utc IS NULL OR status IN ('withdrawn', 'superseded'))
);

CREATE INDEX ix_consent_player_purpose ON governance.consent_record (player_id, purpose, status);

CREATE TABLE governance.data_access_audit (
  access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id TEXT NOT NULL,
  actor_role TEXT NOT NULL,
  purpose governance.consent_purpose NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('allowed', 'denied', 'redacted')),
  accessed_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_id TEXT NOT NULL
);

CREATE TABLE analytics.qualitative_feature_daily (
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  feature_date DATE NOT NULL,
  feature_name TEXT NOT NULL,
  feature_value NUMERIC(8, 5) CHECK (feature_value BETWEEN -1 AND 1),
  event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count >= 0),
  mean_extraction_confidence NUMERIC(5, 4) CHECK (mean_extraction_confidence BETWEEN 0 AND 1),
  source_diversity INTEGER NOT NULL DEFAULT 0 CHECK (source_diversity >= 0),
  days_since_last_observation NUMERIC(8, 2) CHECK (days_since_last_observation >= 0),
  is_missing BOOLEAN NOT NULL DEFAULT TRUE,
  as_of_utc TIMESTAMPTZ NOT NULL,
  taxonomy_version TEXT NOT NULL,
  review_status analytics.review_status NOT NULL DEFAULT 'not_reviewed',
  PRIMARY KEY (player_id, feature_date, feature_name),
  CHECK ((is_missing AND feature_value IS NULL) OR (NOT is_missing AND feature_value IS NOT NULL))
);

CREATE INDEX ix_qual_feature_player_asof ON analytics.qualitative_feature_daily (player_id, as_of_utc DESC);

CREATE TABLE analytics.player_feature_snapshot (
  snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  cutoff_utc TIMESTAMPTZ NOT NULL,
  feature_set_version TEXT NOT NULL,
  quantitative_features JSONB NOT NULL DEFAULT '{}'::jsonb,
  qualitative_features JSONB NOT NULL DEFAULT '{}'::jsonb,
  missingness_features JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_watermark JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (player_id, cutoff_utc, feature_set_version)
);

CREATE INDEX ix_snapshot_player_cutoff ON analytics.player_feature_snapshot (player_id, cutoff_utc DESC);

CREATE TABLE analytics.outcome_observation (
  outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  target_name TEXT NOT NULL,
  window_start_utc TIMESTAMPTZ NOT NULL,
  window_end_utc TIMESTAMPTZ NOT NULL,
  observed_at_utc TIMESTAMPTZ NOT NULL,
  available_at_utc TIMESTAMPTZ NOT NULL,
  target_value NUMERIC(12, 6),
  label_status TEXT NOT NULL DEFAULT 'accepted',
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  UNIQUE (player_id, target_name, window_start_utc, window_end_utc),
  CHECK (window_end_utc > window_start_utc),
  CHECK (available_at_utc >= observed_at_utc)
);

CREATE TABLE analytics.model_prediction (
  prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id UUID NOT NULL REFERENCES core.player(player_id),
  snapshot_id UUID NOT NULL REFERENCES analytics.player_feature_snapshot(snapshot_id),
  target_name TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  predicted_value NUMERIC(12, 6) NOT NULL,
  lower_bound NUMERIC(12, 6),
  upper_bound NUMERIC(12, 6),
  calibration_bucket TEXT,
  explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
  generated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  human_review_status analytics.review_status NOT NULL DEFAULT 'not_reviewed',
  reviewer_note TEXT,
  CHECK (lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound)
);

CREATE INDEX ix_prediction_player_time ON analytics.model_prediction (player_id, generated_at_utc DESC);

CREATE VIEW analytics.v_player_daily_decision_support AS
SELECT
  p.player_code,
  p.age_band,
  p.primary_position,
  s.player_id,
  s.cutoff_utc,
  s.feature_set_version,
  s.quantitative_features,
  s.qualitative_features,
  s.missingness_features,
  s.source_watermark,
  pred.target_name,
  pred.model_name,
  pred.model_version,
  pred.predicted_value,
  pred.lower_bound,
  pred.upper_bound,
  pred.calibration_bucket,
  pred.explanation,
  pred.generated_at_utc,
  pred.human_review_status
FROM analytics.player_feature_snapshot s
JOIN core.player p ON p.player_id = s.player_id
LEFT JOIN LATERAL (
  SELECT mp.*
  FROM analytics.model_prediction mp
  WHERE mp.snapshot_id = s.snapshot_id
  ORDER BY mp.generated_at_utc DESC
  LIMIT 1
) pred ON TRUE;

-- Recommended production hardening (apply in environment-specific migrations):
-- 1. Enable row-level security on governance and analytics tables.
-- 2. Grant raw narrative-derived access only to named roles.
-- 3. Deny direct dashboard access to facts.physical_assessment and governance tables.
-- 4. Attach immutable audit logging to all SELECTs of sensitive fields through the access layer.
