from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.audit import events
from core import governance_events
from tests._pg_semantic_type_isolation import restore_real_semantic_type_rows

_restore_banking_semantic_types = restore_real_semantic_type_rows("banking|")


@pytest.fixture()
def semantic_client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from api.main import app

    with TestClient(app) as client:
        yield client, app


def test_resolve_and_get_semantic_types(semantic_client):
    client, _ = semantic_client

    resp = client.post("/semantic-types/banking/accounts/resolve?schema=src", json={"include_ai": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "banking"
    assert body["schema"] == "src"
    assert body["table"] == "accounts"
    assert body["columns"]
    assert any(column["type_id"] == "currency_code" for column in body["columns"])

    get_resp = client.get("/semantic-types/banking/accounts?schema=src")
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    currency = next(column for column in get_body["columns"] if column["key"].endswith("|currency"))
    assert currency["type_id"] == "currency_code"
    assert "candidates" in currency
    assert "evidence" in currency


def test_resolve_all_resolves_every_table_in_source(semantic_client):
    client, _ = semantic_client

    resp = client.post("/semantic-types/banking/resolve-all", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "banking"
    assert body["table_count"] >= 1
    assert body["column_count"] >= 1

    # The whole-source resolve reaches the accounts table too.
    get_resp = client.get("/semantic-types/banking/accounts?schema=src")
    assert get_resp.status_code == 200
    currency = next(c for c in get_resp.json()["columns"] if c["key"].endswith("|currency"))
    assert currency["type_id"] == "currency_code"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE payload into a list of (event, data) frames."""
    import json
    frames: list[tuple[str, dict]] = []
    event = ""
    for block in text.split("\n\n"):
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if event and data:
            frames.append((event, json.loads(data)))
    return frames


def test_resolve_stream_emits_per_column_progress(semantic_client):
    client, _ = semantic_client

    resp = client.post("/semantic-types/banking/accounts/resolve-stream?schema=src", json={})
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    events_seen = [e for e, _ in frames]

    assert events_seen[0] == "started"
    assert events_seen[-1] == "done"
    column_frames = [d for e, d in frames if e == "column"]
    assert column_frames, "expected at least one per-column progress frame"
    # Each column frame names the column and carries an index within the table total.
    first = column_frames[0]
    assert first["column"]
    assert first["table"] == "accounts"
    assert first["index"] == 1
    assert first["total"] == len(column_frames)
    # The resolve still persists — the currency column resolves as before.
    get_resp = client.get("/semantic-types/banking/accounts?schema=src")
    currency = next(c for c in get_resp.json()["columns"] if c["key"].endswith("|currency"))
    assert currency["type_id"] == "currency_code"


def test_resolve_all_stream_emits_columns_tagged_by_table(semantic_client):
    client, _ = semantic_client

    resp = client.post("/semantic-types/banking/resolve-all-stream", json={})
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    events_seen = [e for e, _ in frames]

    assert events_seen[0] == "started"
    assert events_seen[-1] == "done"
    column_frames = [d for e, d in frames if e == "column"]
    assert column_frames
    # Source-level column frames carry the owning table so the UI can show it.
    assert all(d.get("table") for d in column_frames)
    done = frames[-1][1]
    assert done["table_count"] >= 1
    assert done["column_count"] >= 1


def test_queue_accept_and_audit(semantic_client):
    client, app = semantic_client
    client.post("/semantic-types/banking/accounts/resolve?schema=src", json={"include_ai": False})

    accept_resp = client.post(
        "/semantic-types/banking/accounts/currency/accept?schema=src",
        json={"accepted_by": "tester", "type_id": "currency_code", "domain_role": "code"},
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["accepted_at"]
    assert accept_resp.json()["accepted_by"] == "tester"

    event_types = {event["event_type"] for event in app.state.audit_store.list_events()}
    assert events.SEMANTIC_TYPES_RESOLVED in event_types
    assert events.SEMANTIC_TYPE_ACCEPTED in event_types


def test_accept_refuses_to_leave_type_unresolved(semantic_client):
    """An element can never be accepted without a real governed type (2026-08-20).

    Uses a never-before-seen column key (not a real catalog column) so the store
    creates a fresh default record (type_id 'unresolved') rather than picking up
    any real, already-resolved seed data for this source.
    """
    client, _ = semantic_client

    resp = client.post(
        "/semantic-types/banking/accounts/__never_resolved_test_column__/accept?schema=src",
        json={"accepted_by": "tester"},  # no prior resolve, no type_id override
    )
    assert resp.status_code == 422


def test_accept_override_syncs_domain_role_to_type(semantic_client):
    """Regression: an override that changes the type but sends no domain must not
    leave a stale domain — natural_key must land on natural_id, never a leftover
    surrogate_id (the reported 'Surrogate ID · Natural Key' bug)."""
    client, _ = semantic_client
    client.post("/semantic-types/banking/accounts/resolve?schema=src", json={"include_ai": False})

    resp = client.post(
        "/semantic-types/banking/accounts/currency/accept?schema=src",
        json={"accepted_by": "tester", "type_id": "natural_key"},  # NO domain_role sent
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type_id"] == "natural_key"
    assert body["domain_role"] == "natural_id"


def test_semantic_type_mutations_emit_governance_events(semantic_client):
    """U0 Task 4 — accept/resolve each emit a governance event.

    Zero change to any API response is asserted implicitly: these endpoints
    are exercised identically to test_queue_accept_and_audit above.
    """
    client, _ = semantic_client
    received: dict[str, list[dict]] = {
        events.SEMANTIC_TYPES_RESOLVED: [],
        events.SEMANTIC_TYPE_ACCEPTED: [],
    }
    for event_type in received:
        governance_events.register(event_type, lambda payload, et=event_type: received[et].append(payload))

    try:
        client.post("/semantic-types/banking/accounts/resolve?schema=src", json={"include_ai": False})
        client.post(
            "/semantic-types/banking/accounts/currency/accept?schema=src",
            json={"accepted_by": "tester", "type_id": "currency_code", "domain_role": "code"},
        )
    finally:
        governance_events.clear()

    assert received[events.SEMANTIC_TYPES_RESOLVED], "resolve did not emit a governance event"
    assert received[events.SEMANTIC_TYPE_ACCEPTED], "accept did not emit a governance event"
