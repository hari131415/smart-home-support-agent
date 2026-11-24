-- Views behind the Looker Studio dashboard.

-- Daily volume, handoff rate, cost and latency by prompt version.
CREATE OR REPLACE VIEW support_agent.v_daily AS
SELECT
  DATE(started_at)                                  AS day,
  prompt_version,
  model,
  COUNT(*)                                          AS runs,
  ROUND(COUNTIF(handed_off) / COUNT(*), 4)          AS handoff_rate,
  ROUND(SUM(cost_usd), 4)                           AS cost_usd,
  ROUND(SUM(cost_usd) / COUNT(*), 6)                AS cost_per_run,
  ROUND(AVG(input_tokens + output_tokens), 0)       AS avg_tokens,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(50)]     AS p50_ms,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)]     AS p95_ms
FROM support_agent.agent_runs
GROUP BY day, prompt_version, model;

-- Why are we handing off? Guardrail reasons carry a suffix (e.g. low_confidence:0.42),
-- so group on the prefix.
CREATE OR REPLACE VIEW support_agent.v_handoff_reasons AS
SELECT
  DATE(started_at)                           AS day,
  SPLIT(handoff_reason, ':')[OFFSET(0)]      AS reason,
  COUNT(*)                                   AS n
FROM support_agent.agent_runs
WHERE handed_off
GROUP BY day, reason;

-- Tool usage and failure rate.
CREATE OR REPLACE VIEW support_agent.v_tools AS
SELECT
  DATE(started_at)                         AS day,
  name                                     AS tool,
  COUNT(*)                                 AS calls,
  COUNTIF(error IS NOT NULL)               AS errors,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] AS p95_ms
FROM support_agent.agent_spans
WHERE kind = 'tool'
GROUP BY day, tool;

-- Most-cited manual sections: tells the docs team what customers actually need.
CREATE OR REPLACE VIEW support_agent.v_top_citations AS
SELECT
  citation,
  COUNT(*) AS n
FROM support_agent.agent_runs, UNNEST(citations) AS citation
WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND NOT STARTS_WITH(citation, 'device:')
GROUP BY citation
ORDER BY n DESC;
