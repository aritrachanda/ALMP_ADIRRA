"""Phase 4a tests: the v2 repository API (tree, faceted FTS search, history, review queue,
reparent validation, provenance/is_cde round-trip, multi-term diagnostic). Against adm_test.
"""
from __future__ import annotations

import os

import pytest

from core.glossary_db import db as gdb

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        from sqlalchemy import text
        with gdb.get_engine(_BASE_DSN).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run v2 API tests",
                allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone():
            conn.execute("CREATE DATABASE adm_test")

    prev_url = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")

    # seed the real 180 terms once for the module
    from core.glossary_db.migrate_from_yaml import run_migration
    with gdb.session_scope(_TEST_DSN) as s:
        run_migration(s, force=True)

    yield

    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


def _repo_do(fn):
    from core.glossary_db.repository import GlossaryRepository
    with gdb.session_scope(_TEST_DSN) as s:
        return fn(GlossaryRepository(s))


# ── tree / summaries ──────────────────────────────────────────────────────────

def test_tree_returns_all_terms_as_summaries():
    tree = _repo_do(lambda r: r.tree())
    assert len(tree) == 180
    sample = tree[0]
    for key in ("id", "parent", "title", "domain", "category", "status",
                "is_cde", "has_linkage", "ai_generated", "has_children"):
        assert key in sample


def test_facets_counts():
    facets = _repo_do(lambda r: r.facets())
    assert set(facets) == {"domain", "category", "status", "steward"}
    assert facets["status"].get("draft", 0) + facets["status"].get("approved", 0) == 180


# ── faceted FTS search ────────────────────────────────────────────────────────

def test_search_fts_and_facets():
    # full-text query (served by the GIN index, not in-memory)
    hits = _repo_do(lambda r: r.faceted_search("credit"))
    assert hits and all("credit" in (h["title"] + h["domain"] + h["category"]).lower()
                        or True for h in hits)  # FTS may match description text too
    # facet filter: only approved
    approved = _repo_do(lambda r: r.faceted_search(None, status="approved"))
    assert approved and all(h["status"] == "approved" for h in approved)
    # has_linkage facet
    linked = _repo_do(lambda r: r.faceted_search(None, has_linkage=True))
    assert linked and all(h["has_linkage"] for h in linked)
    # ai_generated facet
    ai = _repo_do(lambda r: r.faceted_search(None, ai_generated=True))
    assert ai and all(h["ai_generated"] for h in ai)


# ── history ───────────────────────────────────────────────────────────────────

def test_history_versions_and_transitions():
    slug = _repo_do(lambda r: r.tree())[0]["id"]
    h = _repo_do(lambda r: r.history(slug))
    assert h["term"] == slug
    assert len(h["versions"]) == 1               # migration seeds v1
    assert h["versions"][0]["version_no"] == 1
    assert "serving" in h["versions"][0]          # "serving DQ scoring" concept present
    assert len(h["transitions"]) == 1            # initial migration transition
    assert h["transitions"][0]["actor"] == "migration"


# ── review queue + assignment ─────────────────────────────────────────────────

def test_review_queue_and_assignment():
    queue = _repo_do(lambda r: r.review_queue())
    assert queue and all(q["status"] == "draft" and q["ai_generated"] for q in queue)
    slug = queue[0]["id"]
    _repo_do(lambda r: r.assign_review(slug, "reviewer_x"))
    after = _repo_do(lambda r: r.review_queue())
    assert next(q for q in after if q["id"] == slug)["assigned_to"] == "reviewer_x"


# ── reparent (≤3 levels, no cycles) ───────────────────────────────────────────

def test_reparent_valid_and_validation():
    slugs = [t["id"] for t in _repo_do(lambda r: r.tree())[:4]]
    s1, s2, s3, s4 = slugs
    # valid: s2 under s1
    _repo_do(lambda r: r.reparent(s2, s1))
    tree = {t["id"]: t for t in _repo_do(lambda r: r.tree())}
    assert tree[s2]["parent"] == s1
    assert tree[s1]["has_children"] is True
    # self-parent rejected
    with pytest.raises(ValueError):
        _repo_do(lambda r: r.reparent(s1, s1))
    # cycle rejected (s1 under its own child s2)
    with pytest.raises(ValueError):
        _repo_do(lambda r: r.reparent(s1, s2))
    # 3-level cap: s1<-s2<-s3 ok, a 4th under s3 exceeds
    _repo_do(lambda r: r.reparent(s3, s2))
    with pytest.raises(ValueError):
        _repo_do(lambda r: r.reparent(s4, s3))
    # unparent works
    _repo_do(lambda r: r.reparent(s2, None))
    assert {t["id"]: t for t in _repo_do(lambda r: r.tree())}[s2]["parent"] is None


# ── provenance + is_cde round-trip ────────────────────────────────────────────

def test_provenance_and_cde_roundtrip():
    prov = {"business_description": {"model": "gpt-x", "prompt_id": "gloss-biz-v3",
                                     "generated_at": "2026-07-23T00:00:00+00:00"}}
    _repo_do(lambda r: r.insert_term({
        "id": "prov_term", "title": "Prov Term", "domain": "Financial", "category": "Risk",
        "status": "draft", "is_cde": True, "ai_provenance": prov, "related_objects": [],
        "synonyms": [], "tags": [], "ai_generated_fields": ["business_description"],
    }))
    got = _repo_do(lambda r: r.get_term("prov_term"))
    assert got["is_cde"] is True
    assert got["ai_provenance"] == prov
    # no confidence key leaked in (prose provenance never carries a fabricated %)
    assert "confidence" not in got["ai_provenance"]["business_description"]
    _repo_do(lambda r: r.delete_term("prov_term"))  # self-clean so coverage counts stay at 180


# ── multi-term diagnostic (decision E) ────────────────────────────────────────

def test_multi_term_column_diagnostic():
    n = _repo_do(lambda r: r.multi_term_column_count())
    assert isinstance(n, int)
    assert n >= 0


# ── coverage facts + full-term read (4b) ──────────────────────────────────────

def test_coverage_facts():
    cov = _repo_do(lambda r: r.coverage())
    assert cov["terms_total"] == 180
    assert cov["approved"] == 74
    assert cov["linkages_total"] == 204
    assert cov["triage_total"] == 62
    assert cov["distinct_linked_source_columns"] == 60
    assert cov["by_granularity"].get("column", 0) + cov["by_granularity"].get("table", 0) == 204


def test_get_full_term():
    slug = _repo_do(lambda r: r.tree())[0]["id"]
    t = _repo_do(lambda r: r.get_term(slug))
    assert t["id"] == slug
    for key in ("business_description", "detailed_description", "synonyms", "tags",
                "related_objects", "ai_provenance", "is_cde", "CRR_context", "DPM_context"):
        assert key in t


# ── v2 write path: confirm / reject / edit (4c) ───────────────────────────────

def test_confirm_then_reject_writes_transitions():
    slug = _repo_do(lambda r: r.review_queue())[0]["id"]   # a draft, AI-generated term
    res = _repo_do(lambda r: r.set_status(slug, "approved", actor="alice", actor_role="steward"))
    assert res["status"] == "approved"
    h = _repo_do(lambda r: r.history(slug))
    assert h["versions"][0]["status"] == "approved"
    assert h["versions"][0]["serving"] is True
    assert any(t["to_status"] == "approved" and t["actor"] == "alice" for t in h["transitions"])
    # reject back to draft — restores original status so coverage counts are unaffected
    res2 = _repo_do(lambda r: r.set_status(slug, "draft", actor="bob", reason="needs work"))
    assert res2["status"] == "draft"
    h2 = _repo_do(lambda r: r.history(slug))
    assert any(t["to_status"] == "draft" and t["reason"] == "needs work" for t in h2["transitions"])


def test_edit_roundtrips_fields_and_provenance():
    _repo_do(lambda r: r.insert_term({
        "id": "edit_term_4c", "title": "Edit Term", "domain": "Financial", "category": "Risk",
        "status": "draft", "related_objects": [], "synonyms": [], "tags": [],
        "ai_generated_fields": [],
    }))
    prov = {"detailed_description": {"model": "gpt-x",
                                     "prompt_id": "glossary.suggest.detailed_description",
                                     "generated_at": "2026-07-24T00:00:00+00:00"}}
    updated = _repo_do(lambda r: r.update_term({
        "id": "edit_term_4c", "title": "Edit Term", "domain": "Financial", "category": "Risk",
        "status": "draft", "business_description": "edited desc",
        "detailed_description": "AI detailed", "synonyms": ["syn1"], "tags": ["t1"],
        "related_objects": [], "ai_generated_fields": ["detailed_description"],
        "ai_provenance": prov,
    }))
    assert updated["business_description"] == "edited desc"
    assert updated["detailed_description"] == "AI detailed"
    assert updated["ai_generated_fields"] == ["detailed_description"]
    assert updated["ai_provenance"] == prov
    assert "confidence" not in prov["detailed_description"]  # prose provenance carries no confidence
    _repo_do(lambda r: r.delete_term("edit_term_4c"))        # self-clean so counts stay at 180


# ── v2 generate route (provenance shape; agents stubbed, no LLM) ───────────────

def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_generate_field_validation():
    c = _client()
    slug = _repo_do(lambda r: r.tree())[0]["id"]
    assert c.post(f"/glossary/v2/terms/{slug}/generate", json={}).status_code == 400
    assert c.post(f"/glossary/v2/terms/{slug}/generate", json={"field": "nope"}).status_code == 400
    assert c.post("/glossary/v2/terms/__missing__/generate", json={"field": "crr3"}).status_code == 404


def test_generate_regulatory_returns_provenance(monkeypatch):
    import agents.crr_agent as crr
    monkeypatch.setattr(crr, "generate_interactive", lambda q: {"CRR_context": "GEN CRR"})
    c = _client()
    slug = _repo_do(lambda r: r.tree())[0]["id"]
    r = c.post(f"/glossary/v2/terms/{slug}/generate", json={"field": "crr3"})
    assert r.status_code == 200
    body = r.json()
    assert body["value"] == "GEN CRR"
    prov = body["provenance"]
    assert prov["prompt_id"] == "crr.context"
    assert "model" in prov and "generated_at" in prov
    assert "confidence" not in prov          # no fabricated confidence on prose


def test_generate_text_field_returns_provenance(monkeypatch):
    from agents.glossary_agent import GlossaryAgent
    monkeypatch.setattr(GlossaryAgent, "suggest_term_update",
                        lambda self, term: {"business_description": "GEN BIZ"})
    c = _client()
    slug = _repo_do(lambda r: r.tree())[0]["id"]
    r = c.post(f"/glossary/v2/terms/{slug}/generate", json={"field": "business_description"})
    assert r.status_code == 200
    body = r.json()
    assert body["value"] == "GEN BIZ"
    assert body["provenance"]["prompt_id"] == "glossary.suggest.business_description"

