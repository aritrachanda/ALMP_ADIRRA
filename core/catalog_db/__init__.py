"""Postgres-backed repository for the source catalog (source-catalog YAML -> Postgres migration).

Reuses the shared Postgres connection layer (core.glossary_db.db) and ORM models
(core.shared.models) rather than duplicating a separate engine/session/models setup —
the same pattern already established by core/audit/pg_store.py for a different subsystem
sharing the same database.
"""
from core.catalog_db.db import backend
from core.catalog_db.repository import (
    clear_source_stats,
    clear_table_stats,
    is_profiled,
    list_source_names,
    load_catalog,
    save_catalog,
    upsert_table_profile,
)

__all__ = [
    "backend", "load_catalog", "save_catalog", "upsert_table_profile",
    "clear_table_stats", "clear_source_stats", "is_profiled", "list_source_names",
]
