"""The support agent loop.

A hand-rolled tool-calling loop rather than a framework agent executor. We need
to trace every step with token counts, intercept the final `respond` call to run
output guardrails, and cap steps. Doing that around a 60-line loop is simpler
than doing it around someone else's abstraction.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from support_agent.devices import DeviceStore
from support_agent.guardrails import (
    EMERGENCY_RESPONSE,
    InputVerdict,
    Triage,
    check_input,
    check_output,
)
from support_agent.prompts import Prompt
from support_agent.retrieval import HybridRetriever
from support_agent.tools import ToolContext, build_tools
from support_agent.tracing import CostTable, RunSummary, Sink, Tracer

log = logging.getLogger(__name__)

HANDOFF_MESSAGE = (
    "I want to make sure you get the right answer, so I'm passing this to one of our "
    "support specialists. They'll follow up with you shortly."
)
INJECTION_MESSAGE = (
    "I can only help with questions about Kestrel Home devices. What's going on with your device?"
)


@dataclass
class AgentResult:
    answer: str
    citations: list[str] = field(default_factory=list)
    confidence: float | None = None
    handed_off: bool = False
    handoff_reason: str | None = None
    ticket_id: str | None = None
    tools_called: list[str] = field(default_factory=list)
    trace_id: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass
class AgentSettings:
    model_name: str
    max_steps: int = 6
    min_confidence: float = 0.6
    min_bm25_score: float = 4.0
    top_k: int = 5


class SupportAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        retriever: HybridRetriever,
        devices: DeviceStore,
        prompt: Prompt,
        sink: Sink,
        costs: CostTable,
        settings: AgentSettings,
    ):
        self.llm = llm
        self.retriever = retriever
        self.devices = devices
        self.prompt = prompt
        self.sink = sink
        self.costs = costs
        self.settings = settings

    def run(
        self,
        message: str,
        user_id: str,
        session_id: str = "",
        history: list[BaseMessage] | None = None,
    ) -> AgentResult:
        tracer = Tracer(self.sink, self.costs, self.settings.model_name)
        t = time.perf_counter()
        verdict = check_input(message)
        tracer.record(
            "guardrail",
            "input",
            t,
            input=verdict.redacted_text,
            output={"triage": verdict.triage, "pii": verdict.pii_found},
        )
        result = self._run(verdict, user_id, history or [], tracer)
        result.trace_id = tracer.trace_id
        result.latency_ms = tracer.elapsed_ms
        _, _, result.cost_usd = tracer.totals()
        self._flush(tracer, result, verdict, user_id, session_id)
        return result

    # ------------------------------------------------------------------

    def _run(self, verdict: InputVerdict, user_id: str, history, tracer: Tracer) -> AgentResult:
        if verdict.triage is Triage.EMERGENCY:
            return AgentResult(
                answer=EMERGENCY_RESPONSE, handed_off=True, handoff_reason="safety_emergency"
            )
        if verdict.triage is Triage.INJECTION:
            return AgentResult(answer=INJECTION_MESSAGE, handoff_reason="prompt_injection")

        ctx = ToolContext(
            user_id=user_id,
            retriever=self.retriever,
            devices=self.devices,
            top_k=self.settings.top_k,
        )
        tools = {tool.name: tool for tool in build_tools(ctx)}
        llm = self.llm.bind_tools(list(tools.values()))
        messages: list[BaseMessage] = [
            SystemMessage(self.prompt.text),
            *history,
            HumanMessage(verdict.redacted_text),
        ]
        called: list[str] = []

        for _ in range(self.settings.max_steps):
            t = time.perf_counter()
            try:
                ai: AIMessage = llm.invoke(messages)
            except Exception as exc:  # noqa: BLE001
                tracer.record("llm", self.settings.model_name, t, error=repr(exc))
                log.exception("llm call failed")
                return self._handoff("llm_error", called)

            usage = ai.usage_metadata or {}
            tracer.record(
                "llm",
                self.settings.model_name,
                t,
                output={"content": ai.content, "tool_calls": ai.tool_calls},
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
            messages.append(ai)

            if not ai.tool_calls:
                # Model answered in plain text instead of calling respond. Treat
                # it as an ungrounded answer so the output check decides.
                return self._finish(str(ai.content), [], 0.5, ctx, called, tracer)

            for call in ai.tool_calls:
                name, args = call["name"], call["args"]
                called.append(name)

                if name == "respond":
                    return self._finish(
                        args.get("answer", ""),
                        args.get("citations", []),
                        float(args.get("confidence", 0.0)),
                        ctx,
                        called,
                        tracer,
                    )

                t = time.perf_counter()
                tool = tools.get(name)
                if tool is None:
                    output, err = f"Unknown tool {name}", "unknown_tool"
                else:
                    try:
                        output, err = tool.invoke(args), None
                    except Exception as exc:  # noqa: BLE001
                        output, err = f"Tool error: {exc}", repr(exc)
                tracer.record("tool", name, t, input=args, output=output, error=err)
                messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))

                if name == "escalate_to_human" and ctx.escalation:
                    return AgentResult(
                        answer=HANDOFF_MESSAGE,
                        handed_off=True,
                        handoff_reason=ctx.escalation["reason"],
                        ticket_id=ctx.escalation["ticket_id"],
                        tools_called=called,
                    )

        return self._handoff("max_steps", called)

    def _finish(self, answer, citations, confidence, ctx: ToolContext, called, tracer: Tracer):
        t = time.perf_counter()
        verdict = check_output(
            answer, citations, confidence, ctx.retrieved_ids, self.settings.min_confidence
        )
        # Manual-only answers need real lexical evidence; device-status answers don't.
        cites_manual = any(not c.startswith("device:") for c in citations)
        if verdict.ok and cites_manual and ctx.best_bm25 < self.settings.min_bm25_score:
            verdict.ok, verdict.reason = False, f"weak_retrieval:{ctx.best_bm25:.1f}"

        tracer.record(
            "guardrail",
            "output",
            t,
            input={"citations": citations, "confidence": confidence},
            output={"ok": verdict.ok, "reason": verdict.reason},
        )
        if not verdict.ok:
            return self._handoff(verdict.reason, called, confidence=confidence)
        return AgentResult(
            answer=answer, citations=citations, confidence=confidence, tools_called=called
        )

    @staticmethod
    def _handoff(reason: str, called: list[str], confidence: float | None = None) -> AgentResult:
        return AgentResult(
            answer=HANDOFF_MESSAGE,
            handed_off=True,
            handoff_reason=reason,
            confidence=confidence,
            tools_called=called,
        )

    def _flush(
        self, tracer: Tracer, r: AgentResult, verdict: InputVerdict, user_id: str, session_id: str
    ):
        it, ot, cost = tracer.totals()
        tracer.flush(
            RunSummary(
                trace_id=tracer.trace_id,
                session_id=session_id,
                user_id=user_id,
                started_at=tracer.started_at,
                latency_ms=tracer.elapsed_ms,
                model=self.settings.model_name,
                prompt_version=self.prompt.version,
                prompt_hash=self.prompt.hash,
                question=verdict.redacted_text,
                answer=r.answer,
                citations=r.citations,
                confidence=r.confidence,
                handed_off=r.handed_off,
                handoff_reason=r.handoff_reason,
                steps=len(tracer.spans),
                tool_calls=sum(1 for s in tracer.spans if s.kind == "tool"),
                input_tokens=it,
                output_tokens=ot,
                cost_usd=cost,
                pii_found=verdict.pii_found,
            )
        )


def serialize_result(r: AgentResult) -> dict:
    return json.loads(json.dumps(r.__dict__, default=str))
