"""Phase 4d cutover tests.

Two guarantees:
- The status vocabulary is pinned in one place and the consumers import it (retirement gate #4).
- Flipping the backend does NOT change the glossary→status index that DQ scoring reads: the
  Postgres view is identical to the YAML view after migration, so the cutover cannot silently
  re-grade the catalog (the flip-invariance test, Postgres-gated).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from core.glossary_db import db as gdb

_ROOT = Path(__file__).resolve().parent.parent
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


# ── pinning (runs everywhere, no database needed) ─────────────────────────────

def test_status_vocabulary_is_pinned():
    from core.glossary_db.status import CANONICAL_STATUSES, CONFIRMED_STATUSES
    assert CANONICAL_STATUSES == ("empty", "draft", "in_review", "approved", "deprecated", "rejected")
    assert "approved" in CONFIRMED_STATUSES
    assert "draft" not in CONFIRMED_STATUSES
    # legacy aliases stay accepted so a stray legacy row scores exactly as before
    assert {"confirmed", "published"} <= CONFIRMED_STATUSES


def test_element_uses_the_pinned_confirmed_set():
    from api.routes import element
    from core.glossary_db.status import CONFIRMED_STATUSES
    assert element._GLOSSARY_CONFIRMED_STATUSES is CONFIRMED_STATUSES


def test_read_api_reads_yaml_when_flag_off(monkeypatch):
    monkeypatch.delenv("ADIRRA_GLOSSARY_BACKEND", raising=False)
    from core.glossary_db import read_api
    terms = read_api.glossary_terms()
    assert isinstance(terms, list) and terms
    assert all("id" in t and "status" in t for t in terms[:5])


# ── flip invariance (Postgres-gated) ──────────────────────────────────────────

@pytest.fixture
def _pg_seeded(monkeypatch):
    """adm_test migrated to head and seeded with the real 180 terms; env points at it."""
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone():
            conn.execute("CREATE DATABASE adm_test")

    monkeypatch.setenv("ADM_DATABASE_URL", _TEST_DSN)
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")

    from core.glossary_db.migrate_from_yaml import run_migration
    with gdb.session_scope(_TEST_DSN) as s:
        run_migration(s, force=True)

    yield _TEST_DSN
    gdb.dispose_all()


def _index_from_terms(terms: list[dict]) -> dict[str, str]:
    """related_object → owning term's status (first-match, mirrors element scoring)."""
    index: dict[str, str] = {}
    for t in terms:
        for ro in t.get("related_objects") or []:
            index.setdefault(ro, t.get("status") or "")
    return index


@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL not reachable")
def test_flip_preserves_glossary_status_index(_pg_seeded, monkeypatch):
    """The glossary→status map DQ scoring consumes is identical yaml vs postgres, so the
    cutover flip changes no column's glossary-linkage sub-score."""
    gl = yaml.safe_load((_ROOT / "glossary" / "glossary.yaml").read_text(encoding="utf-8")) or {}
    yaml_index = _index_from_terms(gl.get("terms", []) or [])

    monkeypatch.setenv("ADIRRA_GLOSSARY_BACKEND", "postgres")
    from core.glossary_db import read_api
    pg_index = _index_from_terms(read_api.glossary_terms())

    assert set(pg_index) == set(yaml_index)
    mismatches = {k: (yaml_index[k], pg_index[k]) for k in yaml_index if pg_index[k] != yaml_index[k]}
    assert not mismatches, f"status drift across the flip: {mismatches}"
