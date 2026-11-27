import json

from .fakes import rag_script, tool_call, tool_outputs


def test_answers_from_manual_with_citation(make_agent, sink):
    agent = make_agent(rag_script())
    r = agent.run("thermostat shows E74", user_id="u-1001", session_id="s1")

    assert not r.handed_off
    assert r.citations and r.citations[0].startswith("thermostat_t3#")
    assert "E74" in r.answer
    assert r.tools_called == ["search_manuals", "respond"]


def test_trace_is_recorded(make_agent, sink):
    agent = make_agent(rag_script())
    r = agent.run("how do I reset the hub", user_id="u-1001", session_id="s2")

    run = sink.runs[-1]
    assert run.trace_id == r.trace_id
    assert run.prompt_version == "v3" and len(run.prompt_hash) == 12
    kinds = [s.kind for s in sink.spans if s.trace_id == r.trace_id]
    assert kinds == ["guardrail", "llm", "tool", "llm", "guardrail"]
    # 2 LLM calls x (900 in, 40 out) at gemini-3.8-flash prices
    assert run.input_tokens == 1800 and run.output_tokens == 80
    assert run.cost_usd == round((1800 * 0.75 + 80 * 3.75) / 1e6, 6)


def test_low_confidence_hands_off(make_agent):
    r = make_agent(rag_script(confidence=0.3)).run("thermostat E74", user_id="u-1001")
    assert r.handed_off and r.handoff_reason.startswith("low_confidence")


def test_hallucinated_citation_hands_off(make_agent):
    r = make_agent(rag_script(cite="thermostat_t3#nonexistent")).run(
        "thermostat E74", user_id="u-1001"
    )
    assert r.handed_off and r.handoff_reason.startswith("ungrounded_citations")


def test_emergency_skips_the_model(make_agent):
    agent = make_agent(rag_script())
    r = agent.run("my plug is sparking!!", user_id="u-1001")
    assert r.handed_off and r.handoff_reason == "safety_emergency"
    assert "emergency services" in r.answer
    assert agent.llm.calls == []


def test_pii_never_reaches_model_or_trace(make_agent, sink):
    agent = make_agent(rag_script())
    agent.run("thermostat E74. reach me at bob@example.com", user_id="u-1001")
    sent = " ".join(str(m.content) for call in agent.llm.calls for m in call)
    assert "bob@example.com" not in sent
    assert "bob@example.com" not in json.dumps([s.__dict__ for s in sink.spans])
    assert sink.runs[-1].pii_found == ["EMAIL"]


def test_device_status_flow(make_agent):
    def script(messages):
        outs = tool_outputs(messages)
        if len(outs) == 0:
            return tool_call("list_devices")
        if len(outs) == 1:
            return tool_call("get_device_status", device_id="lock-22c1")
        if len(outs) == 2:
            return tool_call("search_manuals", query="lock offline remote access hub")
        status = json.loads(outs[1])
        return tool_call(
            "respond",
            answer=f"Your lock is offline because its hub {status['hub_id']} has no internet.",
            citations=["device:lock-22c1", "smart_lock_l1#troubleshooting"],
            confidence=0.85,
        )

    r = make_agent(script).run("why is my front door lock offline", user_id="u-1001")
    assert not r.handed_off, r.handoff_reason
    assert "hub-7f3a" in r.answer
    assert r.tools_called[:2] == ["list_devices", "get_device_status"]


def test_cannot_read_other_users_devices(make_agent):
    seen = {}

    def script(messages):
        outs = tool_outputs(messages)
        if not outs:
            # u-1003 asking about u-1001's lock
            return tool_call("get_device_status", device_id="lock-22c1")
        seen["output"] = outs[0]
        return tool_call(
            "respond", answer="I can't find that device.", citations=[], confidence=0.9
        )

    make_agent(script).run("status of lock-22c1?", user_id="u-1003")
    assert "No device" in seen["output"]
    assert "64" not in seen["output"]


def test_escalation_tool_creates_ticket(make_agent):
    def script(messages):
        return tool_call("escalate_to_human", reason="refund", summary="wants refund")

    r = make_agent(script).run("I want a refund", user_id="u-1001")
    assert r.handed_off and r.handoff_reason == "refund"
    assert r.ticket_id.startswith("SUP-")


def test_max_steps_hands_off(make_agent):
    r = make_agent(lambda m: tool_call("search_manuals", query="again"), max_steps=3).run(
        "thermostat", user_id="u-1001"
    )
    assert r.handed_off and r.handoff_reason == "max_steps"


def test_llm_error_hands_off(make_agent, sink):
    def boom(messages):
        raise RuntimeError("quota exceeded")

    r = make_agent(boom).run("thermostat E74", user_id="u-1001")
    assert r.handed_off and r.handoff_reason == "llm_error"
    assert any(s.error for s in sink.spans)


def test_plain_text_answer_without_respond_is_not_trusted(make_agent):
    from langchain_core.messages import AIMessage

    r = make_agent(lambda m: AIMessage(content="Just restart it.")).run(
        "thermostat broken", user_id="u-1001"
    )
    assert r.handed_off


def test_weak_retrieval_hands_off(make_agent):
    # A question with almost no overlap with the manuals gets a tiny BM25 score.
    r = make_agent(rag_script()).run("zzz qqq", user_id="u-1001")
    assert r.handed_off and r.handoff_reason.startswith("weak_retrieval")
