"""Catalog backend flag + connection helpers.

Reuses the shared Postgres connection layer (core.glossary_db.db) rather than duplicating a
separate engine/session setup — same precedent already established by core/audit/pg_store.py
for a different, unrelated subsystem sharing the same database.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]


def _project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def backend() -> str:
    """Return the configured catalog backend: 'yaml' (default) or 'postgres'.

    ``ADIRRA_CATALOG_BACKEND`` env var wins when set (mirrors ADIRRA_GLOSSARY_BACKEND's pattern);
    otherwise falls back to project.yaml's database.catalog_backend, defaulting to 'yaml' so
    the app's behavior is unchanged until a user explicitly flips it.
    """
    env = os.environ.get("ADIRRA_CATALOG_BACKEND")
    if env:
        return env.strip().lower()
    db = _project().get("database", {}) or {}
    return str(db.get("catalog_backend", "yaml")).strip().lower()
