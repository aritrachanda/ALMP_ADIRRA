"""Focused API tests for the read-only Reference Dataspace register.

Since 5b.3.3 the register is built from the per-code ``reference_code`` store
(``published_register`` — ``in_review`` + ``approved`` only), enriched with business
names + semantic types. These tests stub the repo so they need no live Postgres.

``element_state.set_business_name`` below is a content method though (Postgres-only since
Slice F) -- it lands wherever ``ADM_DATABASE_URL``/project.yaml already points (this file makes
no assumption about which database that is), so clean up the row before/after each test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementDefinition

    def _wipe():
        try:
            with session_scope() as s:
                s.execute(delete(ElementDefinition).where(
                    ElementDefinition.element_key == "demo|public|payments|currency"))
        except Exception:
            pass  # Postgres unreachable -- tests below will fail on their own merits

    _wipe()
    yield
    _wipe()


class _FakeReferenceCodeRepo:
    """In-memory stand-in exposing only ``published_register`` (what the endpoint uses)."""

    def __init__(self, register: list[dict]) -> None:
        self._register = register

    def published_register(self, source: str | None = None) -> list[dict]:
        if source is None:
            return self._register
        return [e for e in self._register if e["element_key"].split("|", 1)[0] == source]


def _code(code, meaning, status, origin, approved_by=None, approved_at=None):
    return {
        "code": code, "value": None, "meaning": meaning, "status": status, "origin": origin,
        "submitted_at": None, "submitted_by": None,
        "approved_at": approved_at, "approved_by": approved_by,
    }


REGISTER = [
    {
        "element_key": "demo|public|payments|currency",
        "codes": [
            _code("EUR", "Euro", "approved", "profiled", "alice", "2026-01-01T00:00:00"),
            _code("USD", "US dollar", "approved", "declared", "alice", "2026-01-02T00:00:00"),
        ],
    },
    {
        "element_key": "demo|public|payments|payment_status",
        "codes": [
            _code("P", "Paid", "in_review", "profiled"),
        ],
    },
]


@pytest.fixture()
def reference_client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_ELEMENT_STATE", str(tmp_path / "element_states.yaml"))
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from api.main import app

    with TestClient(app) as client:
        app.state.reference_code_repo = _FakeReferenceCodeRepo(REGISTER)
        store = app.state.semantic_type_store
        store.set_proposed(
            source="demo", schema="public", table="payments", column="currency",
            type_id="currency_code", domain_role="code", confidence=0.95,
        )
        store.set_proposed(
            source="demo", schema="public", table="payments", column="payment_status",
            type_id="reference_code", domain_role="code", confidence=0.95,
        )
        element_state = app.state.element_state
        element_state.set_business_name("demo", "public", "payments", "currency", "Payment currency")
        yield client


def test_reference_dataspace_builds_register_from_published_codes(reference_client):
    response = reference_client.get("/reference-data")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_fields": 2,
        "status_counts": {"in_review": 1, "approved": 1},
        "gaps": 0,
        "approved_codes": 2,
        "in_review_codes": 1,
        "codes_of_record": 2,
    }
    fields = body["sources"][0]["schemas"][0]["tables"][0]["fields"]
    assert [field["column"] for field in fields] == ["currency", "payment_status"]

    currency = fields[0]
    assert currency["business_name"] == "Payment currency"
    assert currency["business_name_is_fallback"] is False
    assert currency["semantic_type"] == "currency_code"
    assert currency["status"] == "approved"          # all codes approved → frozen set
    assert currency["code_source"] == "reference_code"
    assert currency["counts"] == {
        "total": 2, "documented": 2, "approved": 2, "in_review": 0, "rogue": 0, "unused": 0,
    }
    assert currency["approved_by"] == "alice"
    assert currency["approved_at"] == "2026-01-01T00:00:00"
    assert currency["codes"][0] == {
        "code": "EUR", "value": None, "meaning": "Euro", "status": "approved",
        "origin": "profiled", "share_pct": None, "in_source": True, "in_list": True,
    }
    assert currency["asset_link"] == "/workspace?source=demo&schema=public&table=payments&column=currency&tab=refdata"

    payment_status = fields[1]
    assert payment_status["business_name"] == "Payment Status"
    assert payment_status["business_name_is_fallback"] is True
    assert payment_status["status"] == "in_review"    # any code in review → pending
    assert payment_status["approved_by"] is None


def test_reference_dataspace_filters(reference_client):
    body = reference_client.get(
        "/reference-data", params={"semantic_type": "currency_code", "q": "euro"}
    ).json()
    assert body["summary"]["total_fields"] == 1
    assert body["sources"][0]["schemas"][0]["tables"][0]["fields"][0]["column"] == "currency"

    in_review = reference_client.get("/reference-data", params={"status": "in_review"}).json()
    assert in_review["summary"]["total_fields"] == 1
    assert in_review["sources"][0]["schemas"][0]["tables"][0]["fields"][0]["column"] == "payment_status"


def test_reference_dataspace_source_filter(reference_client):
    both = reference_client.get("/reference-data", params={"source": "demo"}).json()
    assert both["summary"]["total_fields"] == 2

    none = reference_client.get("/reference-data", params={"source": "other"}).json()
    assert none == {
        "summary": {
            "total_fields": 0,
            "status_counts": {"in_review": 0, "approved": 0},
            "gaps": 0,
            "approved_codes": 0,
            "in_review_codes": 0,
            "codes_of_record": 0,
        },
        "sources": [],
    }