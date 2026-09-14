-- Flyweight research platform schema, PostgreSQL/Supabase compatible.
-- No huge checkpoints, traces or replays belong in this database.

CREATE TABLE IF NOT EXISTS schema_info (
  version integer NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiments (
  id text PRIMARY KEY,
  kind text NOT NULL,
  title text NOT NULL,
  status text NOT NULL,
  config_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id text PRIMARY KEY,
  experiment_id text NOT NULL REFERENCES experiments(id),
  trainer text NOT NULL,
  seed integer NOT NULL,
  status text NOT NULL,
  config_json jsonb NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz
);

CREATE TABLE IF NOT EXISTS candidates (
  id text PRIMARY KEY,
  parent_id text REFERENCES candidates(id),
  parent_champion_id text,
  run_id text REFERENCES runs(id),
  trainer text NOT NULL,
  trainer_version text NOT NULL,
  training_seed integer NOT NULL,
  graph_condition text NOT NULL,
  graph_hash text NOT NULL,
  scenario_version text NOT NULL,
  reward_version text NOT NULL,
  generation integer NOT NULL,
  training_metrics_json jsonb NOT NULL,
  validation_metrics_json jsonb NOT NULL,
  checkpoint_hash text NOT NULL,
  checkpoint_id text NOT NULL,
  status text NOT NULL,
  reason_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS champions (
  id text PRIMARY KEY,
  candidate_id text NOT NULL REFERENCES candidates(id),
  checkpoint_id text NOT NULL,
  checkpoint_hash text NOT NULL,
  graph_hash text NOT NULL,
  promoted_at timestamptz NOT NULL,
  selection text NOT NULL,
  evidence_json jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_champion (
  singleton boolean PRIMARY KEY DEFAULT true,
  champion_id text NOT NULL REFERENCES champions(id),
  updated_at timestamptz NOT NULL,
  CHECK (singleton)
);

CREATE TABLE IF NOT EXISTS evaluations (
  id text PRIMARY KEY,
  candidate_id text REFERENCES candidates(id),
  champion_id text REFERENCES champions(id),
  suite text NOT NULL,
  scenario_version text NOT NULL,
  reward_version text NOT NULL,
  metrics_json jsonb NOT NULL,
  rows_json jsonb NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS ladder_certifications (
  id text PRIMARY KEY,
  level_version text NOT NULL,
  champion_id text REFERENCES champions(id),
  checkpoint_hash text NOT NULL,
  scenario_suite text NOT NULL,
  result_json jsonb NOT NULL,
  passed boolean NOT NULL,
  code_commit text NOT NULL,
  graph_hash text NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS topology_conditions (
  id text PRIMARY KEY,
  experiment_id text REFERENCES experiments(id),
  condition text NOT NULL,
  graph_hash text NOT NULL,
  control_hash text NOT NULL,
  config_json jsonb NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_reports (
  id text PRIMARY KEY,
  project_day integer NOT NULL,
  report_date date NOT NULL,
  report_json jsonb NOT NULL,
  summary_text text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL,
  UNIQUE(project_day, report_date)
);

CREATE TABLE IF NOT EXISTS human_matches (
  id text PRIMARY KEY,
  session_id text NOT NULL UNIQUE,
  champion_id text NOT NULL REFERENCES champions(id),
  match_seed integer NOT NULL,
  scenario text NOT NULL,
  result_json jsonb NOT NULL,
  replay_hash text NOT NULL,
  verified boolean NOT NULL,
  tag text NOT NULL CHECK (tag = 'HUMAN_EXHIBITION'),
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS human_sessions (
  session_id text PRIMARY KEY,
  champion_id text NOT NULL,
  checkpoint_hash text NOT NULL,
  match_seed integer NOT NULL,
  scenario text NOT NULL,
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  used boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS leaderboard_entries (
  id text PRIMARY KEY,
  human_match_id text NOT NULL REFERENCES human_matches(id),
  nickname text NOT NULL,
  metric text NOT NULL,
  value double precision NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_leases (
  name text PRIMARY KEY,
  owner text NOT NULL,
  expires_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_status (
  name text PRIMARY KEY,
  owner text NOT NULL,
  state text NOT NULL,
  experiment_id text,
  message text NOT NULL DEFAULT '',
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  heartbeat_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_metadata (
  id text PRIMARY KEY,
  artifact_type text NOT NULL,
  sha256 text NOT NULL,
  bytes bigint NOT NULL,
  storage_key text NOT NULL UNIQUE,
  experiment_id text REFERENCES experiments(id),
  candidate_id text REFERENCES candidates(id),
  champion_id text REFERENCES champions(id),
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_ladder_created ON ladder_certifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_reports_day ON daily_reports(project_day DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_sha ON artifact_metadata(sha256);
