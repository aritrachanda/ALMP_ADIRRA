"""Audit log foundation — append-only event store (DuckDB or Postgres, flag-selected)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from core.audit.store import AuditStore, get_current_store, set_current_store

__all__ = ["AuditStore", "set_current_store", "get_current_store", "audit_backend", "make_audit_store"]

_ROOT = Path(__file__).resolve().parents[2]

#: Cache of the project.yaml audit_backend value (does not change without a restart).
_PROJECT_BACKEND_CACHE: str | None = None


def audit_backend() -> str:
    """Return the configured audit backend: 'duckdb' (default) or 'postgres'.

    ``ADIRRA_AUDIT_BACKEND`` env var wins (live, per-call — used by tests). Otherwise the
    ``project.yaml`` ``database.audit_backend`` value is read once and cached.
    """
    env = os.environ.get("ADIRRA_AUDIT_BACKEND")
    if env:
        return env.strip().lower()
    global _PROJECT_BACKEND_CACHE
    if _PROJECT_BACKEND_CACHE is None:
        try:
            with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
                db = (yaml.safe_load(fh) or {}).get("database", {}) or {}
            _PROJECT_BACKEND_CACHE = str(db.get("audit_backend", "duckdb")).strip().lower()
        except Exception:
            _PROJECT_BACKEND_CACHE = "duckdb"
    return _PROJECT_BACKEND_CACHE


def make_audit_store(duckdb_path: Path | str):
    """Build the audit store for the active backend.

    Default 'duckdb' keeps the existing DuckDB store (byte-identical behaviour). When the
    flag is 'postgres', returns the Postgres-backed store — which holds no process-lifetime
    file lock, so a second ``uvicorn`` no longer fails on the audit DB.
    """
    if audit_backend() == "postgres":
        from core.audit.pg_store import PgAuditStore
        return PgAuditStore()
    return AuditStore(duckdb_path)
