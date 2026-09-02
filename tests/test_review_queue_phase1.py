"""Tests for Phase 1 — queue read-projection API.

Covers:
  - element.py:  submit / approve / reject endpoints
  - semantic_types.py:  submit endpoint
  - review_queue.py:  GET /review-queue/{source}
  - store collection queries: get_pending_review on ElementStateStore

``set_description`` in ``TestElementStatePendingReview`` below is a content method
(Postgres-only since Slice F) -- it lands wherever ``ADM_DATABASE_URL``/project.yaml already
points (this file makes no assumption about which database that is, since the API tests
further down rely on real seeded catalog data), so just clean up its own test keys.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.audit import events as audit_events
from core.element_state import ElementStateStore
from tests._pg_semantic_type_isolation import restore_real_element_definitions, restore_real_semantic_type_rows

_restore_banking_semantic_types = restore_real_semantic_type_rows("banking|")
_restore_banking_definitions = restore_real_element_definitions("banking|")


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementDefinition

    def _wipe():
        try:
            with session_scope() as s:
                s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.like("db%|pub|tbl|%")))
        except Exception:
            pass  # Postgres unreachable -- tests below will fail on their own merits

    _wipe()
    yield
    _wipe()


# ── Store unit tests ──────────────────────────────────────────────────────────


class TestElementStatePendingReview:
    def test_empty_when_nothing_submitted(self, tmp_path: Path):
        store = ElementStateStore(tmp_path / "es.yaml")
        store.set("db", "pub", "tbl", "col", "defined")
        assert store.get_pending_review() == []

    def test_returns_submitted_item(self, tmp_path: Path):
        store = ElementStateStore(tmp_path / "es.yaml")
        store.set("db", "pub", "tbl", "col", "defined")
        store.set_description("db", "pub", "tbl", "col", "A description")
        store.submit_for_review("db", "pub", "tbl", "col", submitted_by="alice")

        items = store.get_pending_review()
        assert len(items) == 1
        item = items[0]
        assert item["source"] == "db"
        assert item["schema"] == "pub"
        assert item["table"] == "tbl"
        assert item["column"] == "col"
        assert item["aspect_type"] == "definition"
        assert item["submitted_by"] == "alice"
        assert item["submitted_at"] is not None

    def test_excludes_decided_items(self, tmp_path: Path):
        store = ElementStateStore(tmp_path / "es.yaml")
        store.set("db", "pub", "tbl", "col", "defined")
        store.submit_for_review("db", "pub", "tbl", "col")
        store.approve("db", "pub", "tbl", "col")  # decision is now 'approved'

        assert store.get_pending_review() == []

    def test_source_filter(self, tmp_path: Path):
        store = ElementStateStore(tmp_path / "es.yaml")
        store.set("db1", "pub", "tbl", "col", "defined")
        store.submit_for_review("db1", "pub", "tbl", "col")
        store.set("db2", "pub", "tbl", "col", "defined")
        store.submit_for_review("db2", "pub", "tbl", "col")

        db1_items = store.get_pending_review("db1")
        assert len(db1_items) == 1
        assert db1_items[0]["source"] == "db1"

    def test_provenance_ai_vs_human(self, tmp_path: Path):
        store = ElementStateStore(tmp_path / "es.yaml")
        store.set("db", "pub", "tbl", "ai_col", "defined")
        store.set_description("db", "pub", "tbl", "ai_col", "AI text", is_ai_generated=True)
        store.submit_for_review("db", "pub", "tbl", "ai_col")

        store.set("db", "pub", "tbl", "human_col", "defined")
        store.set_description("db", "pub", "tbl", "human_col", "Human text", is_ai_generated=False)
        store.submit_for_review("db", "pub", "tbl", "human_col")

        items = {i["column"]: i for i in store.get_pending_review()}
        assert items["ai_col"]["provenance"] == "ai_detected"
        assert items["human_col"]["provenance"] == "human_authored"


# ── API tests ────────────────────────────────────────────────────────────────


@pytest.fixture()
def gov_client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_ELEMENT_STATE", str(tmp_path / "element_states.yaml"))
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from api.main import app

    with TestClient(app) as client:
        yield client, app


def _meet_submit_gate(client: TestClient, table: str, column: str, *, schema: str = "src") -> None:
    """Satisfy the Interpretation Set submit gate (B1 1.5): business name + an Accepted
    semantic type, alongside whatever description each test already sets on its own."""
    client.patch(
        f"/element/banking/{table}/{column}/business-name?schema={schema}",
        json={"business_name": column.replace("_", " ").title()},
    )
    client.post(f"/semantic-types/banking/{table}/{column}/confirm?schema={schema}", json={})


class TestDefinitionSubmitEndpoint:
    def test_submit_definition_returns_submission_status(self, gov_client):
        client, app = gov_client
        # Set up a defined element first via the description endpoint
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "International Bank Account Number"},
        )
        _meet_submit_gate(client, "accounts", "iban")

        resp = client.post(
            "/element/banking/accounts/iban/submit?schema=src",
            json={"submitted_by": "alice"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["submission"]["submitted_by"] == "alice"
        assert body["submission"]["submitted_at"] is not None
        assert body["submission"]["decision"] is None

    def test_submit_without_gate_met_returns_409(self, gov_client):
        client, _ = gov_client
        # This column may already carry a real, confirmed business name from genuine past use
        # of the app -- temporarily blank it so the gate check is truly exercised (restored
        # automatically afterward by the module's autouse restore fixture).
        from core.glossary_db.db import session_scope
        from core.shared.models import ElementDefinition
        with session_scope() as s:
            row = s.query(ElementDefinition).filter(
                ElementDefinition.element_key == "banking|src|accounts|iban"
            ).one_or_none()
            if row is not None:
                row.business_name = None

        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "International Bank Account Number"},
        )
        resp = client.post(
            "/element/banking/accounts/iban/submit?schema=src",
            json={"submitted_by": "alice"},
        )
        assert resp.status_code == 409

    def test_submit_is_audited(self, gov_client):
        client, app = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN description"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post(
            "/element/banking/accounts/iban/submit?schema=src",
            json={"submitted_by": "alice"},
        )
        event_types = {e["event_type"] for e in app.state.audit_store.list_events()}
        assert audit_events.ELEMENT_DEFINITION_SUBMITTED in event_types


class TestDefinitionApproveEndpoint:
    def test_approve_sets_state_approved(self, gov_client):
        client, app = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN description"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={})

        resp = client.post(
            "/element/banking/accounts/iban/approve?schema=src",
            json={"decided_by": "steward_bob"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["lifecycle_state"] == "approved"
        assert body["submission"]["decision"] == "approved"
        assert body["submission"]["decided_by"] == "steward_bob"

    def test_approve_is_audited(self, gov_client):
        client, app = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={})
        client.post("/element/banking/accounts/iban/approve?schema=src", json={"decided_by": "bob"})

        event_types = {e["event_type"] for e in app.state.audit_store.list_events()}
        assert audit_events.ELEMENT_DEFINITION_APPROVED in event_types


class TestDefinitionRejectEndpoint:
    def test_reject_reverts_to_defined(self, gov_client):
        client, app = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={})

        resp = client.post(
            "/element/banking/accounts/iban/reject?schema=src",
            json={"decided_by": "steward", "reason": "Needs more context"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["lifecycle_state"] == "defined"
        assert body["submission"]["decision"] == "rejected"
        assert body["submission"]["reject_reason"] == "Needs more context"

    def test_reject_is_audited(self, gov_client):
        client, app = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={})
        client.post("/element/banking/accounts/iban/reject?schema=src", json={"reason": "Too vague"})

        event_types = {e["event_type"] for e in app.state.audit_store.list_events()}
        assert audit_events.ELEMENT_DEFINITION_REJECTED in event_types


class TestReviewQueueEndpoint:
    def test_empty_queue_returns_zero_counts(self, gov_client):
        client, _ = gov_client
        resp = client.get("/review-queue/banking")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["definition_count"] == 0
        assert body["semantic_type_count"] == 0
        assert body["items"] == []

    def test_submitted_definition_appears_in_queue(self, gov_client):
        client, _ = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN column"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={"submitted_by": "alice"})

        resp = client.get("/review-queue/banking")
        assert resp.status_code == 200
        body = resp.json()
        assert body["definition_count"] == 1
        item = body["items"][0]
        assert item["aspect_type"] == "definition"
        assert item["column"] == "iban"
        assert item["submitted_by"] == "alice"
        assert item["bulk_eligible"] is False

    def test_approved_definition_not_in_queue(self, gov_client):
        client, _ = gov_client
        client.patch(
            "/element/banking/accounts/iban/description?schema=src",
            json={"description": "IBAN"},
        )
        _meet_submit_gate(client, "accounts", "iban")
        client.post("/element/banking/accounts/iban/submit?schema=src", json={})
        client.post("/element/banking/accounts/iban/approve?schema=src", json={})

        resp = client.get("/review-queue/banking")
        assert resp.json()["definition_count"] == 0

    def test_queue_is_sorted_by_submission_time(self, gov_client):
        client, _ = gov_client
        # Submit two definitions using real columns from banking.accounts
        client.patch(
            "/element/banking/accounts/account_id/description?schema=src",
            json={"description": "Account identifier"},
        )
        client.patch(
            "/element/banking/accounts/currency/description?schema=src",
            json={"description": "ISO 4217 currency code"},
        )
        _meet_submit_gate(client, "accounts", "account_id")
        _meet_submit_gate(client, "accounts", "currency")
        client.post("/element/banking/accounts/account_id/submit?schema=src", json={})
        client.post("/element/banking/accounts/currency/submit?schema=src", json={})

        resp = client.get("/review-queue/banking")
        items = resp.json()["items"]
        assert len(items) == 2
        # Items should be ordered by submitted_at
        timestamps = [i["submitted_at"] for i in items]
        assert timestamps == sorted(timestamps)

