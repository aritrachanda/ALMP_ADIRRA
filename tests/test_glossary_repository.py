"""Phase 2 tests for the Business Glossary v2 Postgres data-access layer.

Runs against a throwaway ``adm_test`` database on the same container. If Postgres is not
reachable, the whole module is skipped so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os
import threading

import pytest

from core.glossary_db import db as gdb

# ── skip the whole module if Postgres isn't reachable ─────────────────────────
_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        import psycopg  # noqa: F401
        eng = gdb.get_engine(_BASE_DSN)
        from sqlalchemy import text
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run glossary DB tests",
                allow_module_level=True)


_TABLES = ("linkage", "term_relation", "term_version", "term",
           "lifecycle_transition", "review_task", "review_subject", "glossary")


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    """Create adm_test (if needed), migrate it to head, and point the app at it."""
    import psycopg
    from sqlalchemy import text

    # CREATE DATABASE adm_test (idempotent) via an autocommit connection to the base db.
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


@pytest.fixture(autouse=True)
def _clean_tables():
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    with eng.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


# ── helpers ───────────────────────────────────────────────────────────────────

def _repo_do(fn):
    from core.glossary_db.repository import GlossaryRepository
    with gdb.session_scope(_TEST_DSN) as s:
        return fn(GlossaryRepository(s))


def _term(id_, **over):
    d = {
        "id": id_, "domain": "Financial", "category": "Risk", "title": id_.replace("_", " ").title(),
        "business_description": "biz " + id_, "detailed_description": "detailed " + id_,
        "synonyms": ["syn1", "syn2"], "tags": ["t1"], "related_objects": [],
        "steward": "alice", "status": "draft", "CRR_context": "", "DPM_context": "",
        "ai_generated_fields": [], "last_updated": None, "last_reviewed": None,
    }
    d.update(over)
    return d


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_insert_get_delete():
    _repo_do(lambda r: r.insert_term(_term("credit_risk")))
    got = _repo_do(lambda r: r.get_term("credit_risk"))
    assert got is not None
    assert got["title"] == "Credit Risk"
    assert got["domain"] == "Financial"
    assert set(got["synonyms"]) == {"syn1", "syn2"}
    _repo_do(lambda r: r.delete_term("credit_risk"))
    assert _repo_do(lambda r: r.get_term("credit_risk")) is None


def test_insert_duplicate_raises():
    _repo_do(lambda r: r.insert_term(_term("dup")))
    with pytest.raises(ValueError):
        _repo_do(lambda r: r.insert_term(_term("dup")))


def test_update_and_missing():
    _repo_do(lambda r: r.insert_term(_term("t1")))
    _repo_do(lambda r: r.update_term(_term("t1", title="Renamed", status="approved")))
    got = _repo_do(lambda r: r.get_term("t1"))
    assert got["title"] == "Renamed"
    assert got["status"] == "approved"
    with pytest.raises(KeyError):
        _repo_do(lambda r: r.update_term(_term("nope")))


def test_create_d4_empty_when_title_only():
    # D4: a fresh term with only a title (no content, no explicit status) rests at 'empty'.
    d = {**_term("d4_empty"), "business_description": "", "detailed_description": "",
         "synonyms": [], "tags": [], "CRR_context": "", "DPM_context": ""}
    d.pop("status")
    _repo_do(lambda r: r.insert_term(d))
    assert _repo_do(lambda r: r.get_term("d4_empty"))["status"] == "empty"
    _repo_do(lambda r: r.delete_term("d4_empty"))


def test_create_d4_draft_when_content_present():
    # D4: a fresh term that already has content (no explicit status) rests at 'draft'.
    d = {**_term("d4_draft")}  # _term supplies a business_description
    d.pop("status")
    _repo_do(lambda r: r.insert_term(d))
    assert _repo_do(lambda r: r.get_term("d4_draft"))["status"] == "draft"
    _repo_do(lambda r: r.delete_term("d4_draft"))


def test_create_explicit_status_wins_over_d4():
    # An explicit status always wins (edits send the full term incl. status).
    d = {**_term("d4_explicit"), "business_description": "", "status": "approved"}
    _repo_do(lambda r: r.insert_term(d))
    assert _repo_do(lambda r: r.get_term("d4_explicit"))["status"] == "approved"
    _repo_do(lambda r: r.delete_term("d4_explicit"))


def test_delete_missing_raises():
    with pytest.raises(KeyError):
        _repo_do(lambda r: r.delete_term("ghost"))


# ── search parity ─────────────────────────────────────────────────────────────

def test_search_all_tokens_and_domain_haystack():
    _repo_do(lambda r: r.insert_term(_term("alpha", title="Credit Quality Step", domain="Financial")))
    _repo_do(lambda r: r.insert_term(_term("beta", title="Netting Set", domain="Operational")))
    # multi-token, all must be present across the combined haystack (incl. domain)
    hits = _repo_do(lambda r: r.search("credit quality"))
    assert [h["id"] for h in hits] == ["alpha"]
    # token that only appears in the domain field still matches (v1 parity)
    hits2 = _repo_do(lambda r: r.search("operational netting"))
    assert [h["id"] for h in hits2] == ["beta"]
    assert _repo_do(lambda r: r.search("nonexistent")) == []


# ── linkage many-to-many + round-trip ─────────────────────────────────────────

def test_related_objects_roundtrip_and_many_to_many():
    ref = "source|banking|src.counterparties.credit_quality"
    freetext = "Exposure class"
    _repo_do(lambda r: r.insert_term(_term("term_a", related_objects=[ref, freetext])))
    _repo_do(lambda r: r.insert_term(_term("term_b", related_objects=[ref])))

    a = _repo_do(lambda r: r.get_term("term_a"))
    assert ref in a["related_objects"]
    assert freetext in a["related_objects"]  # free-text concept preserved via term_relation

    # two terms reference the same column → both come back (v1 returned only the first)
    both = _repo_do(lambda r: r.cross_references(ref))
    assert {t["id"] for t in both} == {"term_a", "term_b"}


# ── status transition stamps last_reviewed (via the agent, where the rule lives) ─

def test_agent_status_transition_stamps_last_reviewed():
    from agents.glossary_agent import GlossaryAgent, GlossaryTerm
    agent = GlossaryAgent()  # picks up ADIRRA_GLOSSARY_BACKEND=postgres from the fixture
    agent.add(GlossaryTerm.from_dict(_term("rev_term", status="draft")))
    assert agent.get("rev_term").last_reviewed is None
    updated = agent.update(GlossaryTerm.from_dict(_term("rev_term", status="approved")))
    assert updated.last_reviewed is not None
    assert agent.get("rev_term").status == "approved"


# ── concurrency: two writers no longer clobber (v1 whole-file write lost one) ──

def test_concurrent_writers_both_persist():
    errors: list[Exception] = []

    def writer(idx: int):
        try:
            _repo_do(lambda r: r.insert_term(_term(f"conc_{idx}")))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    ids = {t["id"] for t in _repo_do(lambda r: r.list_terms())}
    assert {"conc_0", "conc_1"} <= ids  # BOTH survived — the v1 data-loss path is gone


def test_concurrent_same_term_updates_serialize_without_error():
    _repo_do(lambda r: r.insert_term(_term("shared")))
    errors: list[Exception] = []

    def updater(name: str):
        try:
            _repo_do(lambda r: r.update_term(_term("shared", steward=name)))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=updater, args=(n,)) for n in ("bob", "carol")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    # row-lock serialised them; final steward is one of the two, not a torn write
    assert _repo_do(lambda r: r.get_term("shared"))["steward"] in {"bob", "carol"}


# ── DB-down surface ───────────────────────────────────────────────────────────

def test_health_false_for_unreachable_dsn():
    bad = "postgresql+psycopg://adm:adm_local_dev@localhost:59999/adm"
    assert gdb.health(bad) is False
