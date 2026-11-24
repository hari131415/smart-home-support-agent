from __future__ import annotations

import pytest

from support_agent.agent import AgentSettings, SupportAgent
from support_agent.config import REPO_ROOT, load_config
from support_agent.devices import JsonDeviceStore
from support_agent.ingest import load_manuals
from support_agent.prompts import load_prompt
from support_agent.retrieval import HybridRetriever
from support_agent.tracing import CostTable, MemorySink

from .fakes import ScriptedChatModel


@pytest.fixture(scope="session")
def cfg():
    return load_config(REPO_ROOT / "configs" / "config.yaml")


@pytest.fixture(scope="session")
def chunks(cfg):
    return load_manuals(cfg.path(cfg.retrieval["manuals_dir"]))


@pytest.fixture(scope="session")
def retriever(chunks):
    return HybridRetriever(chunks)


@pytest.fixture(scope="session")
def devices(cfg):
    return JsonDeviceStore(cfg.path(cfg.devices["json_path"]))


@pytest.fixture
def sink():
    return MemorySink()


@pytest.fixture
def make_agent(cfg, retriever, devices, sink):
    def _make(script, **overrides) -> SupportAgent:
        settings = AgentSettings(
            model_name=cfg.llm["model"],
            max_steps=overrides.pop("max_steps", cfg.agent["max_steps"]),
            min_confidence=cfg.agent["min_confidence"],
            min_bm25_score=cfg.retrieval["min_bm25_score"],
        )
        return SupportAgent(
            llm=ScriptedChatModel(script=script, calls=[]),
            retriever=retriever,
            devices=devices,
            prompt=load_prompt(cfg.prompt["version"]),
            sink=sink,
            costs=CostTable(cfg.llm["pricing"]),
            settings=settings,
        )

    return _make
