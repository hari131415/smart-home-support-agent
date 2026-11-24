"""Tools exposed to the model.

Built per request so they can close over the session's user_id and keep track
of which chunks were actually retrieved (the output guardrail checks citations
against that set).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from support_agent.devices import DeviceNotFound, DeviceStore
from support_agent.retrieval import HybridRetriever

# Fields the model doesn't need (and shouldn't echo back to users).
_HIDDEN_FIELDS = {"user_id"}


class SearchArgs(BaseModel):
    query: str = Field(
        description="What to look up, in plain words. Include error codes or LED colors."
    )
    device_type: str | None = Field(
        default=None,
        description=(
            "Optional filter: thermostat, smart_plug, doorbell, smart_lock, hub, bulb, "
            "smoke_alarm, camera"
        ),
    )


class DeviceArgs(BaseModel):
    device_id: str = Field(description="Device id from list_devices, e.g. 'lock-22c1'")


class EscalateArgs(BaseModel):
    reason: str = Field(description="Short reason code, e.g. 'warranty', 'not_covered', 'unsafe'")
    summary: str = Field(description="One or two sentences for the human agent")


class RespondArgs(BaseModel):
    answer: str = Field(description="The reply to the customer")
    citations: list[str] = Field(description="Chunk ids and device:<id> references used")
    confidence: float = Field(ge=0, le=1, description="How well the sources support the answer")


@dataclass
class ToolContext:
    user_id: str
    retriever: HybridRetriever
    devices: DeviceStore
    top_k: int = 5
    retrieved_ids: set[str] = field(default_factory=set)
    best_bm25: float = 0.0
    escalation: dict | None = None


def build_tools(ctx: ToolContext) -> list[StructuredTool]:
    def search_manuals(query: str, device_type: str | None = None) -> str:
        hits = ctx.retriever.search(query, k=ctx.top_k, device_type=device_type)
        ctx.retrieved_ids.update(h.chunk.id for h in hits)
        if hits:
            ctx.best_bm25 = max(ctx.best_bm25, max(h.bm25 for h in hits))
        if not hits:
            return "No matching manual sections."
        return "\n\n---\n\n".join(h.chunk.render() for h in hits)

    def list_devices() -> str:
        devices = ctx.devices.list_devices(ctx.user_id)
        if not devices:
            return "This customer has no registered devices."
        brief = [
            {k: d[k] for k in ("device_id", "name", "device_type", "model", "online")}
            for d in devices
        ]
        return json.dumps(brief)

    def get_device_status(device_id: str) -> str:
        try:
            d = ctx.devices.get_device(ctx.user_id, device_id)
        except DeviceNotFound:
            return f"No device {device_id} on this account."
        return json.dumps({k: v for k, v in d.items() if k not in _HIDDEN_FIELDS}, default=str)

    def escalate_to_human(reason: str, summary: str) -> str:
        ticket = f"SUP-{uuid.uuid4().hex[:8].upper()}"
        ctx.escalation = {"reason": reason, "summary": summary, "ticket_id": ticket}
        return f"Escalated as {ticket}."

    def respond(answer: str, citations: list[str], confidence: float) -> str:
        # Never actually executed: the agent loop intercepts this call.
        return "ok"

    return [
        StructuredTool.from_function(
            search_manuals,
            name="search_manuals",
            description="Search Kestrel device manuals. Returns sections with their ids.",
            args_schema=SearchArgs,
        ),
        StructuredTool.from_function(
            list_devices,
            name="list_devices",
            description="List the customer's registered devices with ids and online state.",
        ),
        StructuredTool.from_function(
            get_device_status,
            name="get_device_status",
            description="Live status for one device: online, battery, error code, signal, firmware",
            args_schema=DeviceArgs,
        ),
        StructuredTool.from_function(
            escalate_to_human,
            name="escalate_to_human",
            description="Hand the conversation to a human support agent.",
            args_schema=EscalateArgs,
        ),
        StructuredTool.from_function(
            respond,
            name="respond",
            description="Send the final answer to the customer. Call exactly once, last.",
            args_schema=RespondArgs,
        ),
    ]
