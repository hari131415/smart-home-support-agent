Raw outputs from the live runs described in the top-level README.

- `run1/`, `run2/`, `run3/`: `evals/run_eval.py --mode full` reports
  (markdown summary and JSON with every failing case and its reason).
- `deployed/`: checks against Cloud Run revision `support-agent-00003-w9f`:
  smoke test, 8 sample requests with full responses and timings, and the
  BigQuery summary of those runs read back from `agent_runs`.

Run 1's `total_cost_usd` is 0 because `gemini-3.8-flash` wasn't in the price
table yet; the README figure is recomputed from its tokens.
