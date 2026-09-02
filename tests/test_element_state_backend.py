"""Phase 5a — ElementStateStore is backend-aware for the lifecycle slice.

yaml mode: behaviour unchanged (legacy draft/defined/approved).
postgres mode: lifecycle methods route to the Postgres review tables with the canonical
Phase-5 vocabulary; the legacy ``reject`` maps to the new ``returned``. Content methods
(descriptions/metadata) always stay in YAML. Postgres cases skipped if the DB is down.
"""
from __future__ import annotations

import os

import pytest

from core.glossary_db import db as gdb
from core.element_state import ElementStateStore

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        import psycopg  # noqa: F401
        from sqlalchemy import text
        with gdb.get_engine(_BASE_DSN).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ── yaml mode: behaviour unchanged (runs anywhere) ───────────────────────────

def test_yaml_mode_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "yaml")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    assert store.get("s", "sc", "t", "c") == "draft"        # legacy default
    store.set("s", "sc", "t", "c", "defined")
    assert store.get("s", "sc", "t", "c") == "defined"


# ── postgres mode ────────────────────────────────────────────────────────────

pg = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL not reachable")


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    if not _pg_available():
        yield
        return
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone():
            conn.execute("CREATE DATABASE adm_test")
    prev = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")
    # Determinism: clear ONLY the element-interpretation lifecycle rows so re-runs
    # against the persistent adm_test DB start clean (glossary/term data untouched).
    from sqlalchemy import text
    with gdb.get_engine(_TEST_DSN).begin() as c:
        c.execute(text("DELETE FROM lifecycle_transition WHERE subject_type='element_interpretation'"))
        c.execute(text(
            "DELETE FROM review_task WHERE review_subject_id IN "
            "(SELECT id FROM review_subject WHERE subject_type='element_interpretation')"
        ))
        c.execute(text("DELETE FROM review_subject WHERE subject_type='element_interpretation'"))
    yield
    gdb.dispose_all()
    if prev is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev


@pg
def test_pg_mode_get_default_and_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    assert store.get("esb", "sc", "t", "new") == "empty"     # canonical default
    store.set("esb", "sc", "t", "s1", "draft")
    assert store.get("esb", "sc", "t", "s1") == "draft"


@pg
def test_pg_mode_submit_approve_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.submit_for_review("esb", "sc", "t", "s2", submitted_by="ana")
    assert store.get("esb", "sc", "t", "s2") == "in_review"
    status = store.get_submission_status("esb", "sc", "t", "s2")
    assert status["submitted_by"] == "ana" and status["decision"] is None
    store.approve("esb", "sc", "t", "s2", decided_by="stew", decided_by_role="data_steward")
    assert store.get("esb", "sc", "t", "s2") == "approved"
    assert store.get_submission_status("esb", "sc", "t", "s2")["decision"] == "approved"


@pg
def test_pg_mode_reject_maps_to_returned(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.submit_for_review("esb", "sc", "t", "s3", submitted_by="ana")
    store.reject("esb", "sc", "t", "s3", decided_by="stew", reason="add detail")
    assert store.get("esb", "sc", "t", "s3") == "returned"          # not 'rejected'
    assert store.get_submission_status("esb", "sc", "t", "s3")["decision"] == "returned"


@pg
def test_pg_mode_pending_review_enriched_with_yaml_content(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    # description lives in YAML; lifecycle in PG — pending list joins both
    store.set_description("esb", "sc", "t", "s4", "a description", is_ai_generated=True)
    store.submit_for_review("esb", "sc", "t", "s4", submitted_by="ana")
    pending = {p["key"]: p for p in store.get_pending_review("esb")}
    item = pending["esb|sc|t|s4"]
    assert item["description"] == "a description"
    assert item["provenance"] == "ai_detected"
    assert item["submitted_by"] == "ana"


# ── Phase 5b.1 canonical set-level actions (save / withdraw / decline) ────────

def test_yaml_mode_save_withdraw_decline(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "yaml")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    # save advances a set WITH content to the draft-equivalent 'defined' (D4 content-gating)
    store.set_description("s", "sc", "t", "c", "a definition")
    store.save("s", "sc", "t", "c")
    assert store.get("s", "sc", "t", "c") == "defined"
    # withdraw clears the submission overlay and stays editable
    store.submit_for_review("s", "sc", "t", "c", submitted_by="ana")
    store.withdraw("s", "sc", "t", "c", actor="ana")
    assert store.get_submission_status("s", "sc", "t", "c")["submitted_at"] is None
    assert store.get("s", "sc", "t", "c") == "defined"
    # decline records an outright rejection but leaves the item editable
    store.decline("s", "sc", "t", "c", decided_by="stew", reason="no")
    assert store.get("s", "sc", "t", "c") == "defined"
    assert store.get_submission_status("s", "sc", "t", "c")["decision"] == "rejected"


@pg
def test_pg_mode_save_content_gated_empty_vs_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    # title-only save (no definition / business name) rests at 'empty' (D4)
    store.save("esb", "sc", "t", "sv0", actor="ana")
    assert store.get("esb", "sc", "t", "sv0") == "empty"
    # a save once content exists rests at 'draft'
    store.set_description("esb", "sc", "t", "sv1", "a definition")
    store.save("esb", "sc", "t", "sv1", actor="ana")
    assert store.get("esb", "sc", "t", "sv1") == "draft"


@pg
def test_pg_mode_withdraw_returns_to_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.submit_for_review("esb", "sc", "t", "wd1", submitted_by="ana")
    assert store.get("esb", "sc", "t", "wd1") == "in_review"
    store.withdraw("esb", "sc", "t", "wd1", actor="ana")
    assert store.get("esb", "sc", "t", "wd1") == "draft"           # spontaneous pull-back


@pg
def test_pg_mode_decline_is_outright_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.submit_for_review("esb", "sc", "t", "dc1", submitted_by="ana")
    store.decline("esb", "sc", "t", "dc1", decided_by="stew", reason="out of scope")
    assert store.get("esb", "sc", "t", "dc1") == "rejected"        # distinct from 'returned'
    assert store.get_submission_status("esb", "sc", "t", "dc1")["decision"] == "rejected"


def test_yaml_mode_revoke_reopens_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "yaml")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.set_description("s", "sc", "t", "rv", "a definition")
    store.submit_for_review("s", "sc", "t", "rv", submitted_by="ana")
    store.approve("s", "sc", "t", "rv", decided_by="stew")
    assert store.get("s", "sc", "t", "rv") == "approved"
    # revoke re-opens an approved set for editing and clears the decision overlay
    store.revoke("s", "sc", "t", "rv", actor="ana")
    assert store.get("s", "sc", "t", "rv") == "defined"
    assert store.get_submission_status("s", "sc", "t", "rv")["decision"] is None


@pg
def test_pg_mode_revoke_returns_to_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.submit_for_review("esb", "sc", "t", "rv1", submitted_by="ana")
    store.approve("esb", "sc", "t", "rv1", decided_by="stew", decided_by_role="data_steward")
    assert store.get("esb", "sc", "t", "rv1") == "approved"
    store.revoke("esb", "sc", "t", "rv1", actor="ana")
    assert store.get("esb", "sc", "t", "rv1") == "draft"           # prior approval pulled back


# ── C2 — collection-query methods must read LIVE content once element_content_backend
# flips too (they used to read the frozen in-memory YAML snapshot unconditionally) ──────

@pg
def test_pg_mode_find_in_source_reads_live_pg_content(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.set("escq", "sc", "t", "fis1", "draft")
    store.set_description("escq", "sc", "t", "fis1", "live pg description")
    results = {r["key"]: r for r in store.find_in_source("escq")}
    assert results["escq|sc|t|fis1"]["description"] == "live pg description"


@pg
def test_pg_mode_get_pending_review_reads_live_pg_content(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.set_description("escq", "sc", "t", "gpr1", "pending pg description", is_ai_generated=True)
    store.submit_for_review("escq", "sc", "t", "gpr1", submitted_by="ana")
    pending = {p["key"]: p for p in store.get_pending_review("escq")}
    item = pending["escq|sc|t|gpr1"]
    assert item["description"] == "pending pg description"
    assert item["provenance"] == "ai_detected"


@pg
def test_pg_mode_search_multi_filter_reads_live_pg_content_and_status(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres")
    store = ElementStateStore(tmp_path / "element_states.yaml")
    store.set("escq", "sc", "t", "smf1", "draft")
    store.set_description("escq", "sc", "t", "smf1", "searchable pg text")
    by_text = {r["key"] for r in store.search_multi_filter(source="escq", description_text="searchable")}
    assert "escq|sc|t|smf1" in by_text
    # Status filtering also reads live Postgres state, not the frozen startup snapshot —
    # a pre-existing bug on the OLDER element_backend flag, fixed in the same pass.
    by_status = {r["key"] for r in store.search_multi_filter(source="escq", state="draft")}
    assert "escq|sc|t|smf1" in by_status

