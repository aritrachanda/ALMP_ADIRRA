"""U2c — Assessment scoping endpoint: API tests.

Covers the set-scope endpoint (single + bulk), the audit trail, and the
event-triggered DQ re-evaluation (descope → the badge becomes "excluded /
unscored"; re-scope → it is scored again). Each mutating test restores the
column to ``in_scope`` so the session-shared element-state file is left clean
for other tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(session_audit_db):
    from api.main import app
    with TestClient(app) as c:
        yield c


def _scope(client: TestClient, columns, scope, **extra):
    return client.post(
        "/element/banking/accounts/scope?schema=src",
        json={"columns": columns, "scope": scope, **extra},
    )


def test_descope_flips_badge_then_rescope_restores(client: TestClient):
    # Baseline — the column scores normally.
    r = client.get("/element/banking/accounts/currency/dq?schema=src")
    assert r.status_code == 200 and r.json()["state"] == "scored"

    try:
        # Descope → persisted fact + audit + governance re-eval.
        r = _scope(client, ["currency"], "out_of_scope",
                   scope_reason="platform-technical field", scoped_by="tester")
        assert r.status_code == 200
        updated = r.json()["updated"]
        assert updated[0]["assessment_scope"] == "out_of_scope"
        assert updated[0]["scope_reason"] == "platform-technical field"

        # Badge is now excluded from assessment (unscored / out_of_scope).
        r = client.get("/element/banking/accounts/currency/dq?schema=src")
        assert r.status_code == 200
        badge = r.json()
        assert badge["state"] == "unscored"
        assert badge["reason"] == "out_of_scope"
    finally:
        # Re-scope → scored again (also restores the shared state file).
        r = _scope(client, ["currency"], "in_scope")
        assert r.status_code == 200

    r = client.get("/element/banking/accounts/currency/dq?schema=src")
    assert r.status_code == 200 and r.json()["state"] == "scored"


def test_bulk_scope_marks_multiple_columns(client: TestClient):
    overview = client.get("/element/banking/accounts/overview?schema=src").json()
    names = [c["name"] for c in overview["columns_summary"][:2]]
    assert len(names) == 2

    try:
        r = _scope(client, names, "out_of_scope", scoped_by="bulk-tester")
        assert r.status_code == 200
        updated = {u["column"]: u for u in r.json()["updated"]}
        assert set(updated) == set(names)
        assert all(u["assessment_scope"] == "out_of_scope" for u in updated.values())

        # The overview now reports both columns out of scope.
        overview2 = client.get("/element/banking/accounts/overview?schema=src").json()
        by_name = {c["name"]: c for c in overview2["columns_summary"]}
        for n in names:
            assert by_name[n]["assessment_scope"] == "out_of_scope"
    finally:
        _scope(client, names, "in_scope")


def test_scope_change_is_audited(client: TestClient):
    try:
        _scope(client, ["currency"], "out_of_scope", scoped_by="auditor")
        events = client.get(
            "/audit/events",
            params={
                "event_type": "assessment_scope.changed",
                "subject_id": "banking:src.accounts.currency",
                "limit": 5,
            },
        ).json()
        assert events, "expected an ASSESSMENT_SCOPE_CHANGED audit event"
        latest = events[0]
        payload = latest.get("payload") or {}
        assert payload.get("new_scope") == "out_of_scope"
        assert payload.get("prior_scope") == "in_scope"
    finally:
        _scope(client, ["currency"], "in_scope")


def test_scope_unknown_column_404(client: TestClient):
    r = _scope(client, ["not_a_real_column"], "out_of_scope")
    assert r.status_code == 404


def test_scope_invalid_value_422(client: TestClient):
    r = _scope(client, ["currency"], "bogus_scope")
    assert r.status_code == 422


def test_scope_empty_columns_422(client: TestClient):
    r = _scope(client, [], "out_of_scope")
    assert r.status_code == 422
