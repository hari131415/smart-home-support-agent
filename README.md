# smart-home-support-agent

A support agent for smart home devices built on Vertex AI Gemini. It answers
troubleshooting questions from device manuals (RAG), checks the customer's actual
device status through tools, and hands off to a human when it isn't sure or the
situation isn't one a bot should handle.

The part I cared most about is the GenAIOps around it:

- **Tracing.** Every model call, tool call and guardrail decision is logged to
  BigQuery with token counts and cost, keyed by prompt version.
- **Guardrails.** PII redaction before anything leaves the process, a hard-coded
  safety path for emergencies, grounding checks on the output, and a human handoff
  when confidence is low.
- **Evals in CI.** A 150-question suite blocks prompt or retrieval changes that
  drop answer accuracy below the agreed threshold.

```
             ┌───────────────────────────── Cloud Run ──────────────────────────────┐
  customer   │  input guardrails        agent loop (Gemini + tools)    output checks │
  ─────────▶ │  PII redact ─▶ triage ─▶ search_manuals / list_devices ─▶ grounded?   │──▶ answer
             │                 │         get_device_status / escalate    confident?  │    or handoff
             │                 └─ emergency ─▶ fixed safety reply + urgent handoff   │
             └────────────┬──────────────────────────┬──────────────────────────────┘
                          │ spans + run summary      │ device lookups
                          ▼                          ▼
              BigQuery: agent_runs, agent_spans   BigQuery: device_status
                          │
                          ▼
              views: cost/day, handoff reasons, tool errors, top cited sections
```

## How a request flows

1. **Input guardrails** (`guardrails.py`). Emails, phone numbers, card numbers,
   addresses and Wi-Fi passwords are replaced with placeholders. The model, the
   traces and the handoff tickets only ever see the redacted text. Messages that
   describe an emergency (gas smell, sparking, an alarm actually sounding) never
   reach the model: they get a fixed "get out and call 911" reply and an urgent
   handoff. Prompt-injection attempts get a polite refusal.
2. **Agent loop** (`agent.py`). A small tool-calling loop with Gemini, capped at
   6 steps. Tools:
   - `search_manuals`: hybrid BM25 + embedding retrieval over manual sections
   - `list_devices` / `get_device_status`: the customer's devices from BigQuery.
     `user_id` comes from the authenticated request and is bound into the tool,
     so the model can't look up another account even if asked to.
   - `escalate_to_human`: creates a ticket and ends the run
   - `respond`: the only way to give a final answer, with citations and a confidence score
3. **Output checks.** The answer is handed off instead of returned if confidence
   is under 0.6, it has no citations, it cites a chunk that was never retrieved,
   retrieval evidence was weak, or it contains advice we never give (e.g. removing
   batteries from a smoke alarm).

Why a hand-rolled loop instead of a framework agent executor: I needed to trace
every step with tokens, intercept the final call for guardrails, and cap steps.
That was easier around ~80 lines I own than around an abstraction that changes
every few releases. LangChain is still used for the model client, message types
and tool schemas.

## Retrieval

Manuals are split one chunk per `##` section, so troubleshooting steps stay
together. Chunk ids (`thermostat_t3#troubleshooting`) are what the agent cites.

BM25 does most of the work because customers type exact error codes and LED
colors ("E74", "blinking red"). Embeddings (`text-embedding-005`) catch the
paraphrases: "it keeps turning on and off" should find "short cycling". The two
rankings are combined with reciprocal rank fusion, so there's no score
calibration to maintain. When the question names a device, search is restricted
to that device's manual. Before that filter, generic sections like "Factory reset"
from the wrong device kept winning.

Embeddings are computed once in CD (`scripts/build_index.py`) and baked into
the image, so cold starts don't call the embedding API.

**About the manuals.** `data/manuals/` ships with sample manuals for a fictional
"Kestrel Home" product line, written to follow the structure of real vendor
manuals, so the repo runs and the evals are reproducible. To use real manuals,
drop PDFs into the same folder with a sidecar `<name>.yaml` containing
`device_type: ...`. PDFs are chunked into overlapping windows because their
headings aren't reliable.

## Evals

`evals/questions.jsonl` has 150 cases:

| category | n | expected behavior |
|---|---|---|
| manual_qa | 106 | answer, containing specific facts from the manual |
| device_status | 14 | call the device tools, answer using live status |
| safety | 12 | immediate handoff with the safety message |
| escalation | 14 | handoff (refunds, warranty, other brands, off-topic, not covered) |
| access_control | 2 | never reveal another account's device data |
| injection | 2 | refuse without leaking the system prompt |

Answers are graded by required facts (`"10 seconds"`, `"E74"`, `"2.4"`), with
alternatives separated by `|`. I tried an LLM judge first. On short factual
answers it was noisier than string matching and cost more than the agent run.
A unit test checks that every graded fact actually appears in the manual section
it's supposed to come from, so the eval set can't silently drift from the docs.

Two levels in CI:

| workflow | when | what | gate |
|---|---|---|---|
| `ci.yml` | every PR | unit tests + offline eval: retrieval hit@5 on BM25, safety triage recall/false positives | hit@5 ≥ 0.90, safety recall = 100%, 0 false positives |
| `eval.yml` | PRs touching prompts, agent, tools, retrieval, manuals or evals | full 150-case run against Gemini, results posted as a PR comment | answer accuracy ≥ 0.85, handoff recall ≥ 0.95, no cross-account leaks |

Current offline numbers: **98.1% retrieval hit@5** (BM25 only; the two misses
are paraphrase questions that the embedding side picks up), **100% safety
recall**, **0% false positives** on the 120 benign questions.

```bash
python evals/run_eval.py --mode offline
GCP_PROJECT=my-proj python evals/run_eval.py --mode full --out report.json
```

## Prompt versioning

Prompts are files in `src/support_agent/prompts/` (`v2.md`, `v3.md`) selected by
`prompt.version` in config. Every run logs the version and a hash of the prompt
text. The hash catches edits made without bumping the version, so eval results and
production metrics can always be tied to an exact prompt.

## Tracing and cost

`agent_runs` gets one row per customer turn (question, answer, citations,
handoff reason, tokens, cost, latency, prompt version). `agent_spans` gets one
row per step. Rows are buffered and written once after the answer is ready, and a
failed insert is logged, never raised. `sql/views.sql` has the dashboard views:
daily cost and handoff rate by prompt version, handoff reasons, tool error rates,
and the most-cited manual sections. The docs team uses that last one to see what
customers actually need.

Token prices live in `configs/config.yaml`, so update them when switching models.

## Running it

```bash
make install
make test            # unit tests, uses a scripted fake model, no GCP needed
make eval            # offline eval
support-agent search "doorbell battery dies in two weeks"   # retrieval only
```

With GCP credentials (`gcloud auth application-default login`):

```bash
export GCP_PROJECT=your-project
bq query --use_legacy_sql=false < sql/tables.sql
bq query --use_legacy_sql=false < sql/views.sql
./scripts/load_device_status.sh

support-agent ask "my front door lock says offline" --user u-1001
make serve   # then POST /chat with an X-User-Id header
```

```bash
curl -s localhost:8080/chat -H 'Content-Type: application/json' -H 'X-User-Id: u-1001' \
  -d '{"session_id":"s1","message":"Why is my kitchen light not responding?"}' | jq
```

## Deploying

`deploy.yml` on merge to main: build the embedding index → build the image →
deploy to Cloud Run with no traffic on a tagged revision → smoke test → shift
traffic. The service is deployed with `--no-allow-unauthenticated`. It sits
behind the API gateway, which validates the customer's session and sets
`X-User-Id`.

Secrets: `GCP_PROJECT`, `WIF_PROVIDER` (Workload Identity Federation, no JSON
keys), `DEPLOY_SA`, `RUNTIME_SA` (Vertex AI user + BigQuery read on
`device_status`, write on the trace tables), `EVAL_SA`.

## Layout

```
src/support_agent/
  agent.py         tool-calling loop, handoff logic
  tools.py         tool definitions bound to the request's user
  retrieval.py     BM25 + dense, reciprocal rank fusion, device filter
  ingest.py        markdown/PDF manuals -> chunks
  guardrails.py    PII redaction, emergency triage, output checks
  tracing.py       spans, run summaries, cost table, BigQuery/JSONL sinks
  devices.py       device status from BigQuery (or JSON locally)
  evaluation.py    grading + offline checks
  prompts/         versioned system prompts
  api.py           FastAPI app for Cloud Run
evals/             question set and runner
sql/               tables and dashboard views
```

## Known gaps

- Conversation history is client-managed (last 6 turns). Fine for chat widgets,
  but if we add email support it'll need a server-side session store.
- The emergency classifier is regex. It's tuned for recall and is tested against
  every benign question in the eval set for false positives, but a small
  classifier would generalize better to new phrasings.
- The fact-based grading can't catch an answer that has the right facts plus an
  extra wrong step. Spot-checking failed and passed traces weekly covers that for now.
