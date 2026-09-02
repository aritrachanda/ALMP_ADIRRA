"""govern-pg-d follow-up -- combined bind+submit+approve flow (2026-08-16 redesign).

Full API-level test: binding a coded field to a shared reference set now leaves any code the
set doesn't recognise fully editable/submittable on its own, while ONE Submit / ONE Approve
click also carries the binding decision itself through its own review lifecycle. Runs against
a throwaway ``adm_test`` database; skipped entirely if Postgres isn't reachable.
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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run this test",
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
    from core.shared.models import (
        ElementReferenceBinding, LifecycleTransition, ReferenceCode, ReferenceSet,
        ReviewSubject, ReviewTask,
    )

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            subj_ids = [r[0] for r in s.execute(
                ReviewSubject.__table__.select().with_only_columns(ReviewSubject.id)
                .where(ReviewSubject.subject_type == "reference_binding",
                       ReviewSubject.subject_ref.like("rbflow%"))
            ).all()]
            if subj_ids:
                s.execute(delete(ReviewTask).where(ReviewTask.review_subject_id.in_(subj_ids)))
            s.execute(delete(LifecycleTransition).where(
                LifecycleTransition.subject_ref.like("rbflow%")))
            s.execute(delete(ReviewSubject).where(
                ReviewSubject.subject_type == "reference_binding",
                ReviewSubject.subject_ref.like("rbflow%")))
            s.execute(delete(ReferenceCode).where(ReferenceCode.element_key.like("rbflow%")))
            s.execute(delete(ElementReferenceBinding).where(
                ElementReferenceBinding.element_key.like("rbflow%")))
            s.execute(delete(ReferenceSet).where(ReferenceSet.set_id == "rbflow_currency"))

    _wipe()
    yield
    _wipe()



def _seed_pg_set() -> None:
    """Seed reference_set/reference_set_entry directly in Postgres — matches the real live
    configuration (both refdata_backend and refset_backend are postgres), unlike a YAML seed
    file which refset_backend=postgres would silently ignore.
    """
    from core.glossary_db.db import session_scope
    from core.shared.models import ReferenceSet, ReferenceSetEntry

    with session_scope(_TEST_DSN) as s:
        row = ReferenceSet(set_id="rbflow_currency", name="Test Currency Codes",
                           kind="standard", standard_ref="ISO 4217", status="approved")
        s.add(row)
        s.flush()
        s.add(ReferenceSetEntry(reference_set_id=row.id, code="EUR", meaning="Euro", status="active"))
        s.add(ReferenceSetEntry(reference_set_id=row.id, code="USD", meaning="US Dollar", status="active"))


@pytest.fixture()
def flow_client(tmp_path, monkeypatch, session_audit_db):
    # Matches the real live configuration: both backends are postgres.
    monkeypatch.setenv("ADIRRA_REFDATA_BACKEND", "postgres")
    monkeypatch.setenv("AI_TIMO_ELEMENT_STATE", str(tmp_path / "element_states.yaml"))
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    _seed_pg_set()

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
        app.state.project["sources"] = [{"name": "rbflow"}]
        app.state.semantic_type_store.accept(
            source="rbflow", schema="public", table="payments", column="currency",
            accepted_by="ana", type_id="currency_code", domain_role="code",
        )
        yield client


def _bind(client, set_id="rbflow_currency"):
    return client.patch(
        "/element/rbflow/payments/currency/reference-data",
        params={"schema": "public"},
        json={"bound_set_id": set_id},
    )


def test_get_after_bind_splits_recognised_and_unrecognised(flow_client):
    _bind(flow_client)
    body = flow_client.get(
        "/element/rbflow/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert body["bound_set_id"] == "rbflow_currency"
    assert body["binding_status"] == "draft"
    by_code = {c["code"]: c for c in body["codes"]}
    assert by_code["EUR"]["governed"] is True
    assert by_code["EUR"]["meaning"] == "Euro"
    assert by_code["USD"]["governed"] is True
    assert by_code["ZZZ"]["governed"] is False
    assert by_code["ZZZ"]["status"] == "empty"


def test_combined_submit_submits_binding_and_unrecognised_code(flow_client):
    _bind(flow_client)
    save = flow_client.put(
        "/element/rbflow/payments/currency/reference-data/codes",
        params={"schema": "public"},
        json={"codes": [{"code": "ZZZ", "meaning": "Placeholder / rogue value"}]},
    )
    assert save.status_code == 200

    submit = flow_client.post(
        "/element/rbflow/payments/currency/reference-data/submit-codes",
        params={"schema": "public"},
        json={"codes": ["ZZZ"], "actor": "ana"},
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["binding_submitted"] is True
    assert body["submitted"] == 1

    refreshed = flow_client.get(
        "/element/rbflow/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert refreshed["binding_status"] == "in_review"
    zzz = next(c for c in refreshed["codes"] if c["code"] == "ZZZ")
    assert zzz["status"] == "in_review"


def test_pure_binding_submit_with_no_unrecognised_codes(flow_client):
    """A field bound to a set that recognises every observed code still submits cleanly."""
    resp = flow_client.patch(
        "/element/rbflow/payments/currency/reference-data",
        params={"schema": "public"},
        json={"bound_set_id": "rbflow_currency"},
    )
    assert resp.status_code == 200

    submit = flow_client.post(
        "/element/rbflow/payments/currency/reference-data/submit-codes",
        params={"schema": "public"},
        json={"codes": [], "actor": "ana"},
    )
    assert submit.status_code == 200
    assert submit.json()["binding_submitted"] is True
    assert submit.json()["submitted"] == 0


def test_combined_approve_approves_binding_and_code(flow_client):
    _bind(flow_client)
    flow_client.put(
        "/element/rbflow/payments/currency/reference-data/codes",
        params={"schema": "public"},
        json={"codes": [{"code": "ZZZ", "meaning": "Placeholder"}]},
    )
    flow_client.post(
        "/element/rbflow/payments/currency/reference-data/submit-codes",
        params={"schema": "public"},
        json={"codes": ["ZZZ"], "actor": "ana"},
    )

    approve = flow_client.post(
        "/element/rbflow/payments/currency/reference-data/approve-codes",
        params={"schema": "public"},
        json={"codes": ["ZZZ"], "actor": "stew", "actor_role": "data_steward"},
    )
    assert approve.status_code == 200
    body = approve.json()
    assert body["binding_approved"] is True
    assert body["approved"] == 1

    refreshed = flow_client.get(
        "/element/rbflow/payments/currency/reference-data", params={"schema": "public"}
    ).json()
    assert refreshed["binding_status"] == "approved"


def test_review_queue_shows_pending_binding(flow_client):
    _bind(flow_client)
    flow_client.post(
        "/element/rbflow/payments/currency/reference-data/submit-codes",
        params={"schema": "public"},
        json={"codes": [], "actor": "ana"},
    )
    queue = flow_client.get("/review-queue/rbflow/reference-codes").json()
    binding_items = [i for i in queue["items"] if i["aspect_type"] == "reference_binding"]
    assert len(binding_items) == 1
    assert "Test Currency Codes" in binding_items[0]["preview"]


def test_saving_a_recognised_code_is_dropped_defensively(flow_client):
    """A stray attempt to save a MASTER-recognised code never creates its own reference_code row."""
    _bind(flow_client)
    save = flow_client.put(
        "/element/rbflow/payments/currency/reference-data/codes",
        params={"schema": "public"},
        json={"codes": [{"code": "EUR", "meaning": "Should not be saved"}]},
    )
    assert save.status_code == 200
    assert save.json()["codes"] == []
