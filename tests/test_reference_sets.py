"""Tests for shared reference sets: read endpoints, binding, and resolution.

ReferenceSetStore is Postgres-only since Slice F — direct store-level unit coverage
(list/get/meanings/values against seeded data) lives in test_reference_set_repo.py; this file
covers the API surface (endpoints, binding, per-field read/write, role gate). Runs against a
throwaway ``adm_test`` database; skipped entirely if Postgres isn't reachable.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from core.glossary_db import db as gdb

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        import psycopg  # noqa: F401
        from sqlalchemy import text
        eng = gdb.get_engine(_BASE_DSN)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run reference-set tests",
                allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone()
        if not exists:
            conn.execute("CREATE DATABASE adm_test")

    prev_url = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    cfg = Config("db/alembic.ini")
    command.upgrade(cfg, "head")

    yield

    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementReferenceBinding, ReferenceSet

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(ElementReferenceBinding).where(
                ElementReferenceBinding.element_key.like("demo|%")))
            s.execute(delete(ReferenceSet).where(
                ReferenceSet.set_id.in_(["iso_4217_currency", "local_channel"])))

    _wipe()
    yield
    _wipe()


def _seed_sets():
    from core.glossary_db.db import session_scope
    from core.shared.models import ReferenceSet, ReferenceSetEntry

    with session_scope(_TEST_DSN) as s:
        currency = ReferenceSet(set_id="iso_4217_currency", name="ISO 4217 Currency Codes",
                                kind="standard", standard_ref="ISO 4217", status="approved")
        s.add(currency)
        s.flush()
        s.add(ReferenceSetEntry(reference_set_id=currency.id, code="EUR", meaning="Euro", status="active"))
        s.add(ReferenceSetEntry(reference_set_id=currency.id, code="USD", meaning="US Dollar", status="active"))
        s.add(ReferenceSetEntry(reference_set_id=currency.id, code="GBP", meaning="Pound Sterling", status="active"))

        channel = ReferenceSet(set_id="local_channel", name="Local channel codes",
                               kind="local", status="candidate")
        s.add(channel)
        s.flush()
        s.add(ReferenceSetEntry(reference_set_id=channel.id, code="WEB", meaning="Web", status="active"))


# --- Endpoints + binding + resolution --------------------------------------

@pytest.fixture()
def bound_client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_ELEMENT_STATE", str(tmp_path / "element_states.yaml"))
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    _seed_sets()
    from api.main import app
    from api.routes import element as element_routes

    catalog = {
        "schemas": [{
            "name": "public",
            "tables": [{
                "table_name": "payments",
                "row_count": 10,
                "columns": [{
                    "name": "currency",
                    "distinct_count": 3,
                    "code_values": [
                        {"value": "EUR", "count": 6},
                        {"value": "USD", "count": 3},
                        {"value": "ZZZ", "count": 1},
                    ],
                }],
            }],
        }],
    }
    monkeypatch.setattr(element_routes, "_load_source_catalog", lambda _p, _s: catalog)
    with TestClient(app) as client:
        app.state.project["sources"] = [{"name": "demo"}]
        app.state.semantic_type_store.set_proposed(
            source="demo", schema="public", table="payments", column="currency",
            type_id="currency_code", domain_role="code", confidence=0.95,
        )
        yield client


def test_list_and_get_reference_sets(bound_client):
    listing = bound_client.get("/reference-sets").json()
    ids = {s["id"] for s in listing["sets"]}
    assert ids == {"iso_4217_currency", "local_channel"}
    currency = next(s for s in listing["sets"] if s["id"] == "iso_4217_currency")
    assert currency["entry_count"] == 3
    assert "entries" not in currency  # summary only

    detail = bound_client.get("/reference-sets/iso_4217_currency").json()
    assert len(detail["entries"]) == 3


def test_get_unknown_reference_set_404(bound_client):
    assert bound_client.get("/reference-sets/does_not_exist").status_code == 404


def test_bind_unknown_set_404_then_unbind(bound_client):
    assert bound_client.patch(
        "/element/demo/payments/currency/reference-data",
        params={"schema": "public"},
        json={"bound_set_id": "ghost_set"},
    ).status_code == 404

    bound_client.patch(
        "/element/demo/payments/currency/reference-data",
        params={"schema": "public"},
        json={"bound_set_id": "iso_4217_currency"},
    )
    unbind = bound_client.patch(
        "/element/demo/payments/currency/reference-data",
        params={"schema": "public"},
        json={"unbind": True},
    )
    assert unbind.status_code == 200
    assert unbind.json()["bound_set_id"] is None
    # The aggregate register no longer reflects field-level set bindings (5b.3.3);
    # verify the unbound state via the surviving per-field read.
    field = bound_client.get(
        "/element/demo/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert field["bound_set_id"] is None
    assert field["set_kind"] == "local"


# --- Per-field endpoint (GET / PATCH) --------------------------------------

def test_per_field_read_reflects_bound_set(bound_client):
    bound_client.patch(
        "/element/demo/payments/currency/reference-data",
        params={"schema": "public"},
        json={"bound_set_id": "iso_4217_currency"},
    )
    body = bound_client.get(
        "/element/demo/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert body["is_coded"] is True
    assert body["bound_set_id"] == "iso_4217_currency"
    assert body["set_kind"] == "standard"
    meanings = {c["code"]: c["meaning"] for c in body["codes"]}
    assert meanings["EUR"] == "Euro"          # resolved from the set
    assert meanings["ZZZ"] is None            # observed but not in the set


def test_per_field_update_persists_meanings_and_status(bound_client, monkeypatch):
    """Inline meanings/status for an unbound field route through reference_code_repo, which
    the route only consults when refdata_backend='postgres' (unaffected by Slice F)."""
    monkeypatch.setenv("ADIRRA_REFDATA_BACKEND", "postgres")
    patch = bound_client.patch(
        "/element/demo/payments/currency/reference-data",
        params={"schema": "public"},
        json={"meanings": {"EUR": "Euro (inline)"}, "status": "under_review"},
    )
    assert patch.status_code == 200
    assert patch.json()["refdata_status"] == "under_review"

    body = bound_client.get(
        "/element/demo/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert body["status"] == "under_review"
    meanings = {c["code"]: c["meaning"] for c in body["codes"]}
    assert meanings["EUR"] == "Euro (inline)"


# --- Read-access gate ------------------------------------------------------

def test_read_gate_allows_missing_and_known_roles(bound_client):
    assert bound_client.get("/reference-data").status_code == 200
    assert bound_client.get("/reference-data", headers={"X-Role": "data_steward"}).status_code == 200
    assert bound_client.get("/reference-sets", headers={"X-Role": "business_user"}).status_code == 200


def test_read_gate_rejects_unknown_role(bound_client):
    assert bound_client.get("/reference-data", headers={"X-Role": "intruder"}).status_code == 403
    assert bound_client.get("/reference-sets", headers={"X-Role": "intruder"}).status_code == 403
    assert bound_client.get(
        "/reference-sets/iso_4217_currency", headers={"X-Role": "intruder"}
    ).status_code == 403

