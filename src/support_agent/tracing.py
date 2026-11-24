"""Per-run tracing: every model call, tool call and guardrail decision.

One row per span goes to `agent_spans`, one summary row per run to
`agent_runs`. That's enough to answer most questions we get asked:
"why did it say that", "what did this cost last week", "how often do we hand off
and why". See sql/views.sql for the dashboards' queries.

Rows are buffered for the run and flushed once at the end, so a slow BigQuery
insert adds latency only after the user already has their answer.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Span:
    trace_id: str
    span_id: str
    step: int
    kind: str  # llm | tool | retrieval | guardrail
    name: str
    started_at: str
    latency_ms: float
    input: str | None = None
    output: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


@dataclass
class RunSummary:
    trace_id: str
    session_id: str
    user_id: str
    started_at: str
    latency_ms: float
    model: str
    prompt_version: str
    prompt_hash: str
    question: str
    answer: str
    citations: list[str]
    confidence: float | None
    handed_off: bool
    handoff_reason: str | None
    steps: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    pii_found: list[str] = field(default_factory=list)


class Sink(Protocol):
    def write(self, run: RunSummary, spans: list[Span]) -> None: ...


class NullSink:
    def write(self, run: RunSummary, spans: list[Span]) -> None:
        pass


class MemorySink:
    def __init__(self):
        self.runs: list[RunSummary] = []
        self.spans: list[Span] = []

    def write(self, run: RunSummary, spans: list[Span]) -> None:
        self.runs.append(run)
        self.spans.extend(spans)


class JsonlSink:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, run: RunSummary, spans: list[Span]) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps({"run": asdict(run), "spans": [asdict(s) for s in spans]}) + "\n")


class BigQuerySink:
    def __init__(self, project: str, runs_table: str, spans_table: str):
        from google.cloud import bigquery

        self._client = bigquery.Client(project=project)
        self._runs = runs_table
        self._spans = spans_table

    def write(self, run: RunSummary, spans: list[Span]) -> None:
        try:
            errs = self._client.insert_rows_json(self._runs, [asdict(run)])
            if spans:
                errs += self._client.insert_rows_json(self._spans, [asdict(s) for s in spans])
            if errs:
                log.error("trace insert errors: %s", errs[:3])
        except Exception:  # noqa: BLE001 - tracing must never break a user request
            log.exception("failed to write trace %s", run.trace_id)


def build_sink(cfg) -> Sink:
    t = cfg.tracing
    if t["sink"] == "bigquery":
        ds = f"{cfg.gcp['project']}.{cfg.gcp['bq_dataset']}"
        return BigQuerySink(
            cfg.gcp["project"], f"{ds}.{t['bq_runs_table']}", f"{ds}.{t['bq_spans_table']}"
        )
    if t["sink"] == "jsonl":
        return JsonlSink(cfg.path(t["jsonl_path"]))
    return NullSink()


class CostTable:
    def __init__(self, pricing: dict[str, dict[str, float]]):
        self.pricing = pricing

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        p = self.pricing.get(model)
        if p is None:
            return 0.0
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def _truncate(v: Any, n: int = 4000) -> str | None:
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "...[truncated]"


class Tracer:
    """Collects spans for one agent run."""

    def __init__(self, sink: Sink, costs: CostTable, model: str):
        self.sink = sink
        self.costs = costs
        self.model = model
        self.trace_id = uuid.uuid4().hex
        self.spans: list[Span] = []
        self._t0 = time.perf_counter()
        self.started_at = now_iso()

    def record(
        self,
        kind: str,
        name: str,
        started: float,
        input: Any = None,
        output: Any = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: str | None = None,
    ) -> Span:
        span = Span(
            trace_id=self.trace_id,
            span_id=uuid.uuid4().hex[:16],
            step=len(self.spans),
            kind=kind,
            name=name,
            started_at=now_iso(),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            input=_truncate(input),
            output=_truncate(output),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self.costs.cost(self.model, input_tokens, output_tokens)
            if kind == "llm"
            else 0.0,
            error=error,
        )
        self.spans.append(span)
        return span

    @property
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def totals(self) -> tuple[int, int, float]:
        it = sum(s.input_tokens for s in self.spans)
        ot = sum(s.output_tokens for s in self.spans)
        return it, ot, round(sum(s.cost_usd for s in self.spans), 6)

    def flush(self, run: RunSummary) -> None:
        self.sink.write(run, self.spans)
