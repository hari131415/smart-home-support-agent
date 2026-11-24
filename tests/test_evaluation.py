from collections import Counter

import pytest

from support_agent.agent import AgentResult
from support_agent.evaluation import (
    Case,
    fact_present,
    grade,
    load_cases,
    retrieval_hit_rate,
    summarize,
    triage_report,
)


@pytest.fixture(scope="module")
def cases(cfg):
    return load_cases(cfg.path(cfg.eval["questions"]))


def test_eval_set_shape(cases):
    assert len(cases) == 150
    assert len({c.id for c in cases}) == 150
    counts = Counter(c.category for c in cases)
    assert counts["manual_qa"] >= 100
    assert counts["safety"] >= 10


def test_expected_chunks_exist(cases, chunks):
    ids = {c.id for c in chunks}
    for case in cases:
        assert set(case.expected_chunks) <= ids, case.id


def test_expected_facts_are_in_the_manuals(cases, chunks):
    """Every fact we grade on must actually be in the cited section."""
    by_id = {c.id: c.text for c in chunks}
    for case in cases:
        if case.category != "manual_qa":
            continue
        text = " ".join(by_id[c] for c in case.expected_chunks)
        for fact in case.must_include:
            assert fact_present(fact, text), (case.id, fact)


def test_fact_alternatives():
    assert fact_present("15 A|15A|1800", "Max load is 1800 W")
    assert not fact_present("15 A|1800", "Max load is fifteen amps")
    assert fact_present("3°F", "at least 3°F  apart")


def test_grade_answer_and_handoff():
    case = Case("q1", "manual_qa", "q", "u", "answer", must_include=["10 seconds"])
    assert grade(case, AgentResult(answer="Hold for 10 seconds.")).passed
    assert not grade(case, AgentResult(answer="Hold it a while.")).passed
    assert not grade(case, AgentResult(answer="x", handed_off=True, handoff_reason="low")).passed

    h = Case("q2", "escalation", "q", "u", "handoff")
    assert grade(h, AgentResult(answer="", handed_off=True)).passed
    assert not grade(h, AgentResult(answer="Sure, here's a refund")).passed


def test_grade_prompt_leak():
    prompt = "You are the support assistant for Kestrel Home smart devices. " * 3
    case = Case("q3", "injection", "q", "u", "refuse")
    assert grade(case, AgentResult(answer="I can only help with devices."), prompt).passed
    assert not grade(case, AgentResult(answer=prompt), prompt).passed


def test_summarize_rates():
    cases = [Case("a", "manual_qa", "", "", "answer"), Case("b", "safety", "", "", "handoff")]
    grades = [grade(cases[0], AgentResult(answer="ok")), grade(cases[1], AgentResult(answer=""))]
    s = summarize(grades, cases)
    assert s["answer_accuracy"] == 1.0 and s["handoff_recall"] == 0.0
    assert len(s["failures"]) == 1


def test_offline_retrieval_gate(cases, retriever, cfg):
    """Same check CI runs. Fails the build if retrieval regresses."""
    r = retrieval_hit_rate(cases, retriever, k=cfg.retrieval["top_k"])
    assert r["hit_rate"] >= cfg.eval["min_retrieval_hit_at_k"], r["misses"]


def test_offline_triage_gate(cases):
    t = triage_report(cases)
    assert t["safety_recall"] == 1.0, t["missed_safety"]
    assert t["false_positive_rate"] == 0.0, t["false_positives"]
