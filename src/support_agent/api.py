"""HTTP API for Cloud Run.

Stateless: the client sends recent history with each turn, so any instance can
serve any request and we don't need session affinity or a session store.

    uvicorn support_agent.api:app --port 8080
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from support_agent.config import get_config
from support_agent.factory import build_agent

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("support_agent.api")

MAX_HISTORY_TURNS = 6


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    handed_off: bool
    handoff_reason: str | None
    ticket_id: str | None
    trace_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent(get_config())
    yield


app = FastAPI(title="smart-home-support-agent", version="0.6.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    x_user_id: str | None = Header(default=None),
) -> ChatResponse:
    # In production the API gateway validates the customer's token and sets
    # X-User-Id. Requests without it never reach the agent.
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing user identity")

    history = [
        HumanMessage(t.content) if t.role == "user" else AIMessage(t.content)
        for t in body.history[-MAX_HISTORY_TURNS * 2 :]
    ]
    result = request.app.state.agent.run(
        body.message, user_id=x_user_id, session_id=body.session_id, history=history
    )
    return ChatResponse(
        answer=result.answer,
        citations=result.citations,
        handed_off=result.handed_off,
        handoff_reason=result.handoff_reason,
        ticket_id=result.ticket_id,
        trace_id=result.trace_id,
    )
