import pytest
from fastapi.testclient import TestClient

from .fakes import rag_script


@pytest.fixture
def client(make_agent, monkeypatch):
    import support_agent.api as api

    agent = make_agent(rag_script())
    monkeypatch.setattr(api, "build_agent", lambda cfg: agent)
    with TestClient(api.app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_chat(client):
    r = client.post(
        "/chat",
        json={"session_id": "s1", "message": "how do I reset the hub"},
        headers={"X-User-Id": "u-1001"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["citations"] and not body["handed_off"]
    assert len(body["trace_id"]) == 32


def test_chat_requires_identity(client):
    r = client.post("/chat", json={"session_id": "s1", "message": "hi"})
    assert r.status_code == 401


def test_history_is_passed_through(client):
    r = client.post(
        "/chat",
        json={
            "session_id": "s1",
            "message": "and how do I reset it?",
            "history": [
                {"role": "user", "content": "my doorbell is flashing red"},
                {"role": "assistant", "content": "That means Wi-Fi failed."},
            ],
        },
        headers={"X-User-Id": "u-1001"},
    )
    assert r.status_code == 200


def test_rejects_huge_message(client):
    r = client.post(
        "/chat", json={"session_id": "s", "message": "x" * 5000}, headers={"X-User-Id": "u-1"}
    )
    assert r.status_code == 422
