"""govern-pg-d follow-up -- ReferenceBindingReviewRepo tests (binding submit/approve lifecycle).

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run binding review tests",
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
    from core.shared.models import LifecycleTransition, ReviewSubject, ReviewTask

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            subj_ids = [r[0] for r in s.execute(
                ReviewSubject.__table__.select().with_only_columns(ReviewSubject.id)
                .where(ReviewSubject.subject_type == "reference_binding",
                       ReviewSubject.subject_ref.like("rbtest%"))
            ).all()]
            if subj_ids:
                s.execute(delete(ReviewTask).where(ReviewTask.review_subject_id.in_(subj_ids)))
            s.execute(delete(LifecycleTransition).where(
                LifecycleTransition.subject_type == "reference_binding",
                LifecycleTransition.subject_ref.like("rbtest%")))
            s.execute(delete(ReviewSubject).where(
                ReviewSubject.subject_type == "reference_binding",
                ReviewSubject.subject_ref.like("rbtest%")))

    _wipe()
    yield
    _wipe()


@pytest.fixture()
def repo():
    from core.reference_binding_review_repo import ReferenceBindingReviewRepo
    return ReferenceBindingReviewRepo(dsn=_TEST_DSN)


def test_default_status_is_draft(repo):
    assert repo.get_status("rbtest_src|s|t|col_a") == "draft"


def test_submit_moves_to_in_review(repo):
    key = "rbtest_src|s|t|col_b"
    repo.submit(key, actor="ana", actor_role="analyst")
    assert repo.get_status(key) == "in_review"
    review = repo.get_review(key)
    assert review["submitted_by"] == "ana"
    assert review["submitted_at"] is not None


def test_approve_moves_to_approved(repo):
    key = "rbtest_src|s|t|col_c"
    repo.submit(key, actor="ana")
    repo.approve(key, decided_by="stew", decided_by_role="data_steward")
    assert repo.get_status(key) == "approved"
    review = repo.get_review(key)
    assert review["decision"] == "approved"
    assert review["decided_by"] == "stew"


def test_withdraw_returns_to_draft(repo):
    key = "rbtest_src|s|t|col_d"
    repo.submit(key, actor="ana")
    assert repo.get_status(key) == "in_review"
    repo.withdraw(key, actor="ana")
    assert repo.get_status(key) == "draft"


def test_revoke_returns_approved_to_draft(repo):
    key = "rbtest_src|s|t|col_e"
    repo.submit(key, actor="ana")
    repo.approve(key, decided_by="stew")
    repo.revoke(key, actor="stew")
    assert repo.get_status(key) == "draft"


def test_reset_to_draft_clears_prior_approval(repo):
    """A fresh Bind to a DIFFERENT set must not inherit a prior approval (2026-08-16)."""
    key = "rbtest_src|s|t|col_f"
    repo.submit(key, actor="ana")
    repo.approve(key, decided_by="stew")
    assert repo.get_status(key) == "approved"
    repo.reset_to_draft(key)
    assert repo.get_status(key) == "draft"


def test_pending_review_lists_only_in_review(repo):
    a, b = "rbtest_src|s|t|col_g", "rbtest_src|s|t|col_h"
    repo.submit(a, actor="ana")
    repo.submit(b, actor="ana")
    repo.approve(b, decided_by="stew")
    pending = {p["key"] for p in repo.pending_review("rbtest_src")}
    assert a in pending
    assert b not in pending
