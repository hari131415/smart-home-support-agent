"""Wire up a SupportAgent from config. Keeps GCP imports out of the core modules."""

from __future__ import annotations

import logging

from support_agent.agent import AgentSettings, SupportAgent
from support_agent.config import Config
from support_agent.devices import build_device_store
from support_agent.prompts import load_prompt
from support_agent.retrieval import build_retriever
from support_agent.tracing import CostTable, Sink, build_sink

log = logging.getLogger(__name__)


def build_llm(cfg: Config):
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = cfg.llm
    return ChatGoogleGenerativeAI(
        model=llm["model"],
        vertexai=True,
        project=cfg.gcp["project"] or None,
        location=llm.get("location", cfg.gcp["location"]),
        temperature=llm["temperature"],
        max_output_tokens=llm["max_output_tokens"],
        max_retries=llm.get("max_retries", 2),
    )


def build_embedder(cfg: Config):
    if not cfg.embeddings.get("enabled", False):
        return None
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=cfg.embeddings["model"],
        vertexai=True,
        project=cfg.gcp["project"] or None,
        location=cfg.gcp["location"],
    )


def settings_from(cfg: Config) -> AgentSettings:
    return AgentSettings(
        model_name=cfg.llm["model"],
        max_steps=cfg.agent["max_steps"],
        min_confidence=cfg.agent["min_confidence"],
        min_bm25_score=cfg.retrieval["min_bm25_score"],
        top_k=cfg.retrieval["top_k"],
    )


def build_agent(cfg: Config, llm=None, embedder=None, sink: Sink | None = None) -> SupportAgent:
    """Anything not passed in is built from config (i.e. real Vertex clients)."""
    llm = llm if llm is not None else build_llm(cfg)
    if embedder is None:
        embedder = build_embedder(cfg)
    return SupportAgent(
        llm=llm,
        retriever=build_retriever(cfg, embedder=embedder),
        devices=build_device_store(cfg),
        prompt=load_prompt(cfg.prompt["version"]),
        sink=sink if sink is not None else build_sink(cfg),
        costs=CostTable(cfg.llm["pricing"]),
        settings=settings_from(cfg),
    )
