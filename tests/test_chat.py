"""Tests for Chat API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_list_conversations(client: TestClient):
    resp = client.get("/chat/conversations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_and_delete_conversation(client: TestClient):
    # Create
    resp = client.post("/chat/conversations")
    assert resp.status_code == 200
    convo = resp.json()
    cid = convo["id"]
    assert "messages" in convo

    # Fetch
    resp = client.get(f"/chat/conversations/{cid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == cid

    # Delete
    resp = client.delete(f"/chat/conversations/{cid}")
    assert resp.status_code == 200

    # Verify gone
    resp = client.get(f"/chat/conversations/{cid}")
    assert resp.status_code == 404


def test_format_chat_error_classifies_and_redacts(monkeypatch):
    from api.routes.chat import _format_chat_error
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "supersecretkeyvalue123456")

    class _Denied(Exception):
        status_code = 403

    out = _format_chat_error(_Denied("boom supersecretkeyvalue123456"), "AZURE_FOUNDRY_KEY")
    assert out["status"] == 403
    assert "access was denied" in out["summary"].lower()
    assert "supersecretkeyvalue123456" not in out["detail"]  # key redacted
    assert "***redacted***" in out["detail"]


def test_send_message_surfaces_backend_error_transiently(client: TestClient, monkeypatch):
    cid = client.post("/chat/conversations").json()["id"]

    class _Denied(Exception):
        status_code = 403

    import agents.chat_agent as ca
    monkeypatch.setattr(ca, "chat", lambda *a, **k: (_ for _ in ()).throw(
        _Denied("403 - Access denied due to Virtual Network/Firewall rules.")))

    resp = client.post(f"/chat/conversations/{cid}/messages", json={"content": "hi"})
    assert resp.status_code == 200
    err = resp.json().get("error")
    assert err and err["status"] == 403
    assert "Firewall" in err["detail"]

    # Ephemeral — the failed assistant turn is NOT persisted; only the user message remains.
    convo = client.get(f"/chat/conversations/{cid}").json()
    assert [m["role"] for m in convo["messages"]] == ["user"]

    client.delete(f"/chat/conversations/{cid}")
