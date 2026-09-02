"""Phase 5a — Postgres-backed element-interpretation lifecycle repo.

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run lifecycle repo tests",
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
    prev_backend = os.environ.get("ADIRRA_GLOSSARY_BACKEND")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    os.environ["ADIRRA_GLOSSARY_BACKEND"] = "postgres"
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
        os.environ.pop("ADIRRA_GLOSSARY_BACKEND", None)
    else:
        os.environ["ADIRRA_GLOSSARY_BACKEND"] = prev_backend


@pytest.fixture()
def repo():
    from core.element_lifecycle_repo import ElementLifecycleRepo
    return ElementLifecycleRepo(dsn=_TEST_DSN)


def _k(col: str) -> str:
    # unique-ish per test column to avoid cross-test interference
    return f"src|sc|t1|{col}"


def test_unknown_key_defaults_to_empty(repo):
    assert repo.get_status(_k("never_touched")) == "empty"


def test_save_sets_draft(repo):
    k = _k("desc1")
    repo.save(k, actor="ana")
    assert repo.get_status(k) == "draft"


def test_submit_then_pending_and_review_overlay(repo):
    k = _k("submit1")
    repo.save(k, actor="ana")
    repo.submit(k, actor="ana")
    assert repo.get_status(k) == "in_review"
    pending = {p["key"] for p in repo.pending_review("src")}
    assert k in pending
    review = repo.get_review(k)
    assert review["submitted_by"] == "ana" and review["submitted_at"] is not None
    assert review["decision"] is None


def test_approve_sets_approved_and_records_decider(repo):
    k = _k("approve1")
    repo.submit(k, actor="ana")
    repo.approve(k, decided_by="stew", decided_by_role="data_steward")
    assert repo.get_status(k) == "approved"
    review = repo.get_review(k)
    assert review["decision"] == "approved" and review["decided_by"] == "stew"
    # no longer pending
    assert k not in {p["key"] for p in repo.pending_review("src")}


def test_reject_sets_rejected_with_reason(repo):
    k = _k("reject1")
    repo.submit(k, actor="ana")
    repo.reject(k, decided_by="stew", reason="not good")
    assert repo.get_status(k) == "rejected"
    assert repo.get_review(k)["reject_reason"] == "not good"


def test_send_back_sets_returned(repo):
    k = _k("return1")
    repo.submit(k, actor="ana")
    repo.send_back(k, decided_by="stew", reason="add detail")
    assert repo.get_status(k) == "returned"
    assert repo.get_review(k)["decision"] == "returned"


def test_withdraw_rests_in_draft_but_audits_withdrawn(repo):
    k = _k("withdraw1")
    repo.submit(k, actor="ana")
    repo.withdraw(k, actor="ana")
    assert repo.get_status(k) == "draft"
    # audit trail keeps the 'withdrawn' action
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import LifecycleTransition
    from sqlalchemy import select
    with session_scope(_TEST_DSN) as s:
        actions = s.execute(
            select(LifecycleTransition.to_status)
            .where(LifecycleTransition.subject_ref == k)
        ).scalars().all()
    assert "withdrawn" in actions


def test_revoke_from_approved_rests_in_draft_and_audits_revoked(repo):
    k = _k("revoke1")
    repo.submit(k, actor="ana")
    repo.approve(k, decided_by="stew")
    repo.revoke(k, actor="stew", reason="wording change")
    assert repo.get_status(k) == "draft"
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import LifecycleTransition
    from sqlalchemy import select
    with session_scope(_TEST_DSN) as s:
        actions = s.execute(
            select(LifecycleTransition.to_status)
            .where(LifecycleTransition.subject_ref == k)
            .order_by(LifecycleTransition.occurred_at)
        ).scalars().all()
    assert actions[-1] == "revoked" and actions[0] == "in_review"


def test_counts_by_state(repo):
    # a fresh source keeps the count deterministic
    repo.save("cnt|sc|t|a", actor="ana")
    repo.save("cnt|sc|t|b", actor="ana")
    repo.submit("cnt|sc|t|c", actor="ana")
    counts = repo.counts_by_state("cnt")
    assert counts.get("draft") == 2 and counts.get("in_review") == 1


def test_set_status_rejects_transition_only_status(repo):
    with pytest.raises(ValueError):
        repo.set_status(_k("bad"), "withdrawn")
