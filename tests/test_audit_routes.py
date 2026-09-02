"""Smoke tests for the audit API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.audit import events


@pytest.fixture()
def seeded_client(session_audit_db, monkeypatch):
    """TestClient with pre-seeded audit events."""
    from api.main import app
    from core.audit import AuditStore, set_current_store

    # Pin to duckdb regardless of the live project.yaml flag (now 'postgres') — otherwise
    # the app resolves a PgAuditStore pointing at the real database instead of this
    # fixture's throwaway seed, and assertions see leftover production events instead.
    monkeypatch.setenv("ADIRRA_AUDIT_BACKEND", "duckdb")

    store = AuditStore(session_audit_db)
    set_current_store(store)
    store.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "term-abc", {"title": "Test Term"})
    store.log_ai_call(
        model="gpt-5.4-mini", subject_type="mapping", subject_id="banking_to_bird",
        prompt_tokens=100, completion_tokens=60, latency_ms=900.0,
    )
    store.close()

    with TestClient(app) as c:
        yield c, app.state.audit_store


def test_list_events_ok(seeded_client):
    c, _ = seeded_client
    resp = c.get("/audit/events")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 2


def test_list_events_filter_class(seeded_client):
    c, _ = seeded_client
    resp = c.get("/audit/events?event_class=ai")
    assert resp.status_code == 200
    body = resp.json()
    assert all(e["event_class"] == "ai" for e in body)
    assert len(body) >= 1


def test_list_events_filter_type(seeded_client):
    c, _ = seeded_client
    resp = c.get(f"/audit/events?event_type={events.GLOSSARY_TERM_CREATED}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["subject_id"] == "term-abc"


def test_get_event_by_id(seeded_client):
    c, store = seeded_client
    all_events = store.list_events()
    assert all_events, "No events in store"
    first_id = all_events[-1]["id"]
    resp = c.get(f"/audit/events/{first_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == first_id


def test_get_event_not_found(seeded_client):
    c, _ = seeded_client
    resp = c.get("/audit/events/999999")
    assert resp.status_code == 404


def test_summary_ok(seeded_client):
    c, _ = seeded_client
    resp = c.get("/audit/summary?days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    types_found = {row["event_type"] for row in body}
    assert events.GLOSSARY_TERM_CREATED in types_found
    assert "ai.call" in types_found
