"""govern-pg-d-reference-sets -- ReferenceSetRepo (Postgres) + ReferenceSetStore/ElementStateStore
backend-branch tests.

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
                ElementReferenceBinding.element_key.like("rstest%")))
            s.execute(delete(ReferenceSet).where(ReferenceSet.set_id.like("rstest%")))

    _wipe()
    yield
    _wipe()


@pytest.fixture()
def repo():
    from core.reference_set_repo import ReferenceSetRepo
    return ReferenceSetRepo(dsn=_TEST_DSN)


def _seed_set(set_id: str, name: str, *, kind: str = "standard", parent_set_id=None,
              entries: list[dict] | None = None):
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import ReferenceSet, ReferenceSetEntry

    with session_scope(_TEST_DSN) as s:
        parent_pk = None
        if parent_set_id:
            parent_pk = s.execute(
                select(ReferenceSet.id).where(ReferenceSet.set_id == parent_set_id)
            ).scalar_one()
        row = ReferenceSet(set_id=set_id, name=name, kind=kind, status="approved",
                           parent_set_id=parent_pk)
        s.add(row)
        s.flush()
        for e in entries or []:
            s.add(ReferenceSetEntry(reference_set_id=row.id, **e))
        return row.id


# ── sets + entries ───────────────────────────────────────────────────────────

def test_list_and_get_match_yaml_shape(repo):
    _seed_set("rstest_currency", "Test Currency Codes", entries=[
        {"code": "USD", "value": "US Dollar", "meaning": "United States currency", "status": "active"},
        {"code": "EUR", "value": "Euro", "meaning": "Eurozone currency", "status": "active"},
    ])

    sets = repo.list()
    ids = {s["id"] for s in sets}
    assert "rstest_currency" in ids

    found = repo.get("rstest_currency")
    assert found["name"] == "Test Currency Codes"
    assert found["kind"] == "standard"
    assert found["status"] == "approved"
    assert found["parent_set_id"] is None
    assert len(found["entries"]) == 2
    codes = {e["code"] for e in found["entries"]}
    assert codes == {"USD", "EUR"}


def test_get_unknown_set_returns_none(repo):
    assert repo.get("rstest_does_not_exist") is None


def test_meanings_and_values(repo):
    _seed_set("rstest_currency", "Test Currency Codes", entries=[
        {"code": "USD", "value": "US Dollar", "meaning": "United States currency", "status": "active"},
    ])
    assert repo.meanings("rstest_currency") == {"USD": "United States currency"}
    assert repo.values("rstest_currency") == {"USD": "US Dollar"}
    assert repo.meanings("rstest_unknown") == {}
    assert repo.values("rstest_unknown") == {}


def test_set_to_set_parent_link(repo):
    _seed_set("rstest_parent", "Parent Set")
    _seed_set("rstest_child", "Child Set", parent_set_id="rstest_parent")

    child = repo.get("rstest_child")
    assert child["parent_set_id"] == "rstest_parent"
    parent = repo.get("rstest_parent")
    assert parent["parent_set_id"] is None


def test_get_returns_deep_copy_not_live_cache(repo):
    _seed_set("rstest_currency", "Test Currency Codes", entries=[
        {"code": "USD", "value": "US Dollar", "meaning": "United States currency", "status": "active"},
    ])
    found = repo.get("rstest_currency")
    found["name"] = "Mutated"
    found["entries"][0]["meaning"] = "Mutated meaning"
    fresh = repo.get("rstest_currency")
    assert fresh["name"] == "Test Currency Codes"
    assert fresh["entries"][0]["meaning"] == "United States currency"


# ── column-to-set binding ────────────────────────────────────────────────────

def test_binding_set_get_clear(repo):
    _seed_set("rstest_currency", "Test Currency Codes")
    key = "rstest_src|s|t|col_a"

    assert repo.get_binding(key) is None
    repo.set_binding(key, "rstest_currency")
    assert repo.get_binding(key) == "rstest_currency"
    repo.clear_binding(key)
    assert repo.get_binding(key) is None


def test_binding_unknown_set_raises(repo):
    with pytest.raises(ValueError):
        repo.set_binding("rstest_src|s|t|col_b", "rstest_no_such_set")


def test_binding_invalidates_cache_immediately(repo):
    _seed_set("rstest_currency", "Test Currency Codes")
    key = "rstest_src|s|t|col_c"
    repo.set_binding(key, "rstest_currency")
    assert repo.get_binding(key) == "rstest_currency"  # not stale until TTL, since we just wrote it
    repo.clear_binding(key)
    assert repo.get_binding(key) is None  # immediately reflects the clear too


# ── ReferenceSetStore backend branch ─────────────────────────────────────────

def test_store_pg_mode_reads_live_postgres(tmp_path, monkeypatch):
    from core.reference_set_repo import ReferenceSetRepo
    ReferenceSetRepo(dsn=_TEST_DSN)  # ensure table exists via fixture; direct-seed below
    _seed_set("rstest_currency", "Test Currency Codes", entries=[
        {"code": "USD", "value": "US Dollar", "meaning": "United States currency", "status": "active"},
    ])

    from core.reference_set_store import ReferenceSetStore
    store = ReferenceSetStore(tmp_path / "reference_sets.yaml")  # file doesn't even exist
    store._repo = ReferenceSetRepo(dsn=_TEST_DSN)  # pin to the test DB, not the live default

    found = store.get("rstest_currency")
    assert found is not None
    assert found["name"] == "Test Currency Codes"
    assert store.meanings("rstest_currency") == {"USD": "United States currency"}


# ── ElementStateStore backend branch (the binding methods) ──────────────────

def test_element_state_pg_mode_binding_roundtrip(tmp_path, monkeypatch):
    _seed_set("rstest_currency", "Test Currency Codes")

    from core.element_state import ElementStateStore
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store._refset_repo_instance = None
    from core.reference_set_repo import ReferenceSetRepo
    store._refset_repo_instance = ReferenceSetRepo(dsn=_TEST_DSN)

    assert store.get_reference_binding("rstest_src2", "s", "t", "col_a") is None
    store.set_reference_binding("rstest_src2", "s", "t", "col_a", "rstest_currency")
    assert store.get_reference_binding("rstest_src2", "s", "t", "col_a") == "rstest_currency"
    store.clear_reference_binding("rstest_src2", "s", "t", "col_a")
    assert store.get_reference_binding("rstest_src2", "s", "t", "col_a") is None
