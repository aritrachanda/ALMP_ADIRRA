"""
Dependency injection helpers for FastAPI routes.

Shared resources are loaded once at startup (via lifespan in main.py)
and stored on ``app.state``. These functions expose them as FastAPI
``Depends(...)`` parameters.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, Request

_ROOT = Path(__file__).resolve().parent.parent

# Ensure core/ and agents/ are importable.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit import AuditStore  # noqa: E402 (after sys.path setup)
from core.semantic_type_store import SemanticTypeStore  # noqa: E402
from core.reference_set_store import ReferenceSetStore  # noqa: E402
from core.element_state import ElementStateStore  # noqa: E402
from core.document_store import DocumentStore  # noqa: E402


def get_project(request: Request) -> dict:
    """Return the parsed ``project.yaml``."""
    return request.app.state.project


def get_connections(request: Request) -> dict:
    """Return the parsed ``connections.yaml``."""
    return request.app.state.connections


def get_root(request: Request) -> Path:
    """Return the repo root path."""
    return request.app.state.root


def get_paths(request: Request) -> dict[str, Path]:
    """Return resolved paths for catalogs, mappings, etc."""
    project: dict = request.app.state.project
    root: Path = request.app.state.root
    paths_cfg = project.get("paths", {})
    return {
        "sources": root / paths_cfg.get("source_catalogs", "sources"),
        "targets": root / paths_cfg.get("target_catalogs", "targets"),
        "mappings": root / paths_cfg.get("mappings", "mappings"),
    }


def get_agent_config(request: Request) -> dict[str, Any]:
    """Return the agent configuration from ``project.yaml``."""
    return request.app.state.project.get("agent", {})


def get_audit_store(request: Request) -> AuditStore:
    """Return the shared AuditStore."""
    return request.app.state.audit_store


def get_element_state(request: Request) -> ElementStateStore:
    """Return the shared ElementStateStore."""
    return request.app.state.element_state


def get_semantic_type_store(request: Request) -> SemanticTypeStore:
    """Return the shared SemanticTypeStore."""
    return request.app.state.semantic_type_store


def get_reference_set_store(request: Request) -> ReferenceSetStore:
    """Return the shared ReferenceSetStore (Phase 3 shared reference sets)."""
    return request.app.state.reference_set_store


def get_reference_code_repo(request: Request):
    """Return the shared ReferenceCodeRepo (Phase 5b.2 per-code Reference Data, Postgres)."""
    return request.app.state.reference_code_repo


def get_reference_binding_review_repo(request: Request):
    """Return the shared ReferenceBindingReviewRepo (binding submit/approve lifecycle)."""
    return request.app.state.reference_binding_review_repo


def get_reference_set_repo(request: Request):
    """Return the shared ReferenceSetRepo (bulk/direct Postgres access, incl. bindings)."""
    return request.app.state.reference_set_repo


def get_document_store(request: Request) -> DocumentStore:
    """Return the shared DocumentStore."""
    return request.app.state.document_store


def get_dq_service(request: Request):
    """Return the shared DQ scoring service, or ``None`` if it failed to init.

    DQ wiring is guarded at startup (a scoring failure never breaks the app),
    so callers must tolerate ``None`` and degrade to an unscored badge.
    """
    return getattr(request.app.state, "dq_service", None)


# Governed session-role vocabulary (mirrors frontend/src/stores/roleStore.ts).
KNOWN_ROLES = frozenset({"data_analyst", "data_architect", "data_steward", "business_user"})


def require_read_access(x_role: str | None = Header(default=None)) -> str:
    """Light read-access gate for governed read endpoints (Phase 5 hardening).

    Reading is broadly allowed: every known session role — and the no-header
    default reader — passes. Only an explicitly present but unknown role is
    rejected. This is a validation seam consistent with the app's non-enforced
    role model, not a full auth layer; it never breaks callers that send no
    ``X-Role`` header.
    """
    role = (x_role or "data_analyst").strip().lower()
    if role not in KNOWN_ROLES:
        raise HTTPException(status_code=403, detail=f"Unknown role '{role}'.")
    return role
