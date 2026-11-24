-- bq query --use_legacy_sql=false --project_id=$GCP_PROJECT < sql/tables.sql

CREATE SCHEMA IF NOT EXISTS support_agent OPTIONS (location = "US");

-- One row per agent run (a single customer turn).
CREATE TABLE IF NOT EXISTS support_agent.agent_runs (
  trace_id        STRING NOT NULL,
  session_id      STRING,
  user_id         STRING,
  started_at      TIMESTAMP NOT NULL,
  latency_ms      FLOAT64,
  model           STRING,
  prompt_version  STRING,
  prompt_hash     STRING,
  question        STRING,   -- already PII-redacted
  answer          STRING,
  citations       ARRAY<STRING>,
  confidence      FLOAT64,
  handed_off      BOOL,
  handoff_reason  STRING,
  steps           INT64,
  tool_calls      INT64,
  input_tokens    INT64,
  output_tokens   INT64,
  cost_usd        FLOAT64,
  pii_found       ARRAY<STRING>
)
PARTITION BY DATE(started_at)
CLUSTER BY prompt_version, handed_off
OPTIONS (partition_expiration_days = 180);

-- One row per step inside a run: model calls, tool calls, guardrail decisions.
CREATE TABLE IF NOT EXISTS support_agent.agent_spans (
  trace_id       STRING NOT NULL,
  span_id        STRING NOT NULL,
  step           INT64,
  kind           STRING,   -- llm | tool | guardrail
  name           STRING,
  started_at     TIMESTAMP,
  latency_ms     FLOAT64,
  input          STRING,
  output         STRING,
  input_tokens   INT64,
  output_tokens  INT64,
  cost_usd       FLOAT64,
  error          STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY trace_id
OPTIONS (partition_expiration_days = 30);

-- Latest device telemetry snapshot. Owned by the device platform team;
-- the agent only reads it.
CREATE TABLE IF NOT EXISTS support_agent.device_status (
  device_id    STRING NOT NULL,
  user_id      STRING NOT NULL,
  name         STRING,
  device_type  STRING,
  model        STRING,
  online       BOOL,
  last_seen    TIMESTAMP,
  battery_pct  INT64,
  firmware     STRING,
  rssi_dbm     INT64,
  error_code   STRING,
  hub_id       STRING
)
CLUSTER BY user_id;
