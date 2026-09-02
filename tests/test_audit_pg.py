"""Audit → Postgres (2026-08-03): PgAuditStore round-trip + factory, against adm_test.

Runs against a throwaway ``adm_test`` database on the same container; the whole module is
skipped if Postgres isn't reachable, so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os

import pytest

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run audit-pg tests",
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
    prev_backend = os.environ.get("ADIRRA_AUDIT_BACKEND")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    os.environ["ADIRRA_AUDIT_BACKEND"] = "postgres"
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
    if prev_backend is None:
        os.environ.pop("ADIRRA_AUDIT_BACKEND", None)
    else:
        os.environ["ADIRRA_AUDIT_BACKEND"] = prev_backend


@pytest.fixture(autouse=True)
def _clean_audit_rows():
    """Wipe test-marked rows before + after each test (idempotent across suite runs)."""
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import AuditEvent

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(AuditEvent).where(AuditEvent.subject_id.like("audittest:%")))

    _wipe()
    yield
    _wipe()


_EXPECTED_KEYS = {
    "id", "occurred_at", "event_class", "event_type",
    "actor_user_id", "actor_role", "legal_entity",
    "subject_type", "subject_id", "payload", "request_id",
}


def test_log_business_roundtrip():
    from core.audit.pg_store import PgAuditStore
    store = PgAuditStore()
    eid = store.log_business(
        "definition.saved", "column", "audittest:banking.customers.id",
        {"note": "hello"}, actor_user_id="tester", actor_role="data_steward",
    )
    assert isinstance(eid, int) and eid > 0

    events = store.list_events(subject_id="audittest:banking.customers.id", limit=10)
    assert len(events) == 1
    ev = events[0]
    assert set(ev.keys()) == _EXPECTED_KEYS       # shape matches the DuckDB store
    assert ev["event_class"] == "business"
    assert ev["event_type"] == "definition.saved"
    assert ev["payload"] == {"note": "hello"}
    assert ev["actor_role"] == "data_steward"
    assert isinstance(ev["occurred_at"], str)     # ISO text, like the DuckDB store

    got = store.get_event(eid)
    assert got is not None and got["id"] == eid


def test_log_ai_call_and_class_filter():
    from core.audit.pg_store import PgAuditStore
    store = PgAuditStore()
    store.log_ai_call(model="gpt-x", subject_type="column", subject_id="audittest:ai.col",
                      prompt_tokens=10, completion_tokens=5, latency_ms=123.4)
    ai = store.list_events(event_class="ai", subject_id="audittest:ai.col")
    assert len(ai) == 1
    assert ai[0]["event_type"] == "ai.call"
    assert ai[0]["payload"]["total_tokens"] == 15


def test_event_prefix_and_summary():
    from core.audit.pg_store import PgAuditStore
    store = PgAuditStore()
    store.log_business("glossary.linked", "term", "audittest:t1", {})
    store.log_business("glossary.confirmed", "term", "audittest:t2", {})
    pref = store.list_events(event_prefix="glossary.", subject_id="audittest:")
    assert len(pref) == 2
    assert isinstance(store.summary(days=1), list)


def test_factory_selects_backend(tmp_path):
    from core.audit import make_audit_store
    from core.audit.pg_store import PgAuditStore
    from core.audit.store import AuditStore

    prev = os.environ.get("ADIRRA_AUDIT_BACKEND")
    try:
        os.environ["ADIRRA_AUDIT_BACKEND"] = "postgres"
        assert isinstance(make_audit_store("ignored.duckdb"), PgAuditStore)

        os.environ["ADIRRA_AUDIT_BACKEND"] = "duckdb"
        st = make_audit_store(str(tmp_path / "audit.duckdb"))
        assert isinstance(st, AuditStore)
        st.close()
    finally:
        if prev is None:
            os.environ.pop("ADIRRA_AUDIT_BACKEND", None)
        else:
            os.environ["ADIRRA_AUDIT_BACKEND"] = prev
