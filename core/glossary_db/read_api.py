"""Backend-aware glossary read surface for the non-agent consumers.

The glossary is served from PostgreSQL when ``database.glossary_backend`` (project.yaml)
/ the ``ADIRRA_GLOSSARY_BACKEND`` env var is ``'postgres'``, otherwise from
``glossary/glossary.yaml``. Historically every consumer (element DQ scoring, semantic
types, dashboard, settings export/import, chat) opened the YAML file directly, which
would silently go stale the moment the backend flag flips. This module is the single
flag-aware read used by all of them so the cutover repoints one place, not seven — and
a flip back to ``yaml`` stays clean.

Returns the flat v1 dict shape (``{'terms': [...]}``) either way: the repository's
``list_terms`` emits exactly the same per-term keys the YAML file carries
(id/title/status/category/related_objects/ai_generated_fields/business_description/…).
"""
from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_YAML_PATH = _ROOT / "glossary" / "glossary.yaml"


def _use_pg() -> bool:
    try:
        from core.glossary_db.db import backend
        return backend() == "postgres"
    except Exception:
        return False


def glossary_terms() -> list[dict]:
    """Every glossary term as a flat v1 dict, from Postgres or YAML per the flag."""
    if _use_pg():
        from core.glossary_db.db import session_scope
        from core.glossary_db.repository import GlossaryRepository
        with session_scope() as session:
            return GlossaryRepository(session).list_terms()
    if not _YAML_PATH.exists():
        return []
    with _YAML_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("terms", []) or []


def glossary_dict() -> dict:
    """The glossary as a flat v1 dict ``{'version': 1, 'terms': [...]}`` (backend-aware)."""
    return {"version": 1, "terms": glossary_terms()}
