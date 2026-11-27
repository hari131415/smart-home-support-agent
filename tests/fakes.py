"""Test doubles for the chat model and embeddings."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

import numpy as np
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

Script = Callable[[list[BaseMessage]], AIMessage]


class ScriptedChatModel(BaseChatModel):
    """Returns whatever `script(messages)` returns. Records every call."""

    script: Script
    calls: list[list[BaseMessage]] = []
    bound: list[tuple[list[str], dict]] = []
    offered: list[list[str]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.script(messages))])

    def bind_tools(self, tools, **kwargs):
        names = [t.name for t in tools]
        self.bound.append((names, kwargs))
        return _Bound(self, names)


class _Bound:
    """What bind_tools returns: remembers which tools were offered on each call."""

    def __init__(self, model: ScriptedChatModel, names: list[str]):
        self.model, self.names = model, names

    def invoke(self, messages):
        self.model.offered.append(self.names)
        return self.model.invoke(messages)


_n = 0


def tool_call(name: str, **args) -> AIMessage:
    global _n
    _n += 1
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call_{_n}"}],
        usage_metadata={"input_tokens": 900, "output_tokens": 40, "total_tokens": 940},
    )


def tool_outputs(messages: list[BaseMessage]) -> list[str]:
    return [m.content for m in messages if isinstance(m, ToolMessage)]


def rag_script(confidence: float = 0.9, cite: str | None = None) -> Script:
    """search_manuals with the user's question, then respond quoting the top chunk."""

    def script(messages):
        outputs = tool_outputs(messages)
        if not outputs:
            return tool_call("search_manuals", query=messages[-1].content)
        top = outputs[-1].split("\n\n---\n\n")[0]
        chunk_id = re.match(r"\[([^\]]+)\]", top).group(1)
        return tool_call("respond", answer=top, citations=[cite or chunk_id], confidence=confidence)

    return script


class HashEmbedder:
    """Deterministic bag-of-words embedding so dense retrieval can be tested offline."""

    dim = 256

    def _vec(self, text: str) -> list[float]:
        v = np.zeros(self.dim)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1
        return v.tolist()

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)
