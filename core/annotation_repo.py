"""Postgres-backed repository for the catalog annotation overlay (govern-pg-e/f-annotations).

Reconstructs/writes the exact same nested dict shape ``core.annotations.load_annotations``/
``save_annotations`` return --
``{"version": 1, "dataset": ..., "annotations": {"schema.table": {"user_description": ...,
"mapping_instructions": ..., "columns": {"col": {...}}}}}`` -- so the existing pure
``get_table_annotations``/``set_table_annotations`` helpers (plain dict manipulation, no I/O)
keep working unchanged.

Storage is split at two granularities, mirroring ``ElementContentRepo``'s own
``ElementDefinition``/``DatasetStory`` split: ``catalog_table_annotation`` (keyed
``source|schema|table``) and ``catalog_column_annotation`` (keyed
``source|schema|table|column``) -- the dict's own dotted ``schema.table`` inner key is purely
this overlay's legacy in-memory shape, not the Postgres storage key.

``save()`` reconciles the WHOLE dataset's stored rows against the dict passed in (upsert what's
present, delete what's no longer there) -- matching the old YAML file's full-file-rewrite
semantics exactly, since every real caller today only ever edits one table before saving the
whole reloaded dict back (never a genuine multi-table bulk write).

The `yaml`-mode branch (and the `annotation_backend` flag) was retired in Slice F, once
`annotation_backend` had been live on Postgres and stable -- this is now the ONLY implementation.

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.glossary_db.db import session_scope
from core.shared.models import CatalogColumnAnnotation, CatalogTableAnnotation


def _split_table_key(key: str) -> tuple[str, str]:
    """Split the dict's own ``"schema.table"`` inner key back into (schema, table)."""
    schema_name, sep, table_name = key.partition(".")
    if not sep:
        return "", schema_name
    return schema_name, table_name


class AnnotationRepo:
    """Data-access for the catalog annotation overlay on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn

    def load(self, dataset_name: str) -> dict[str, Any]:
        """Return the same ``{"version", "dataset", "annotations"}`` shape as the YAML store."""
        prefix = f"{dataset_name}|"
        annotations: dict[str, dict[str, Any]] = {}
        with session_scope(self._dsn) as s:
            table_rows = s.execute(
                select(CatalogTableAnnotation)
                .where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%"))
            ).scalars().all()
            for row in table_rows:
                _, schema_name, table_name = row.dataset_key.split("|", 2)
                # Matches get_table_annotations' own key construction exactly (always
                # "schema.table", never special-cased for an empty schema) so a real
                # dataset with no recorded schema still round-trips byte-for-byte.
                key = f"{schema_name}.{table_name}"
                entry = annotations.setdefault(key, {})
                if row.user_description:
                    entry["user_description"] = row.user_description
                if row.mapping_instructions:
                    entry["mapping_instructions"] = row.mapping_instructions

            col_rows = s.execute(
                select(CatalogColumnAnnotation)
                .where(CatalogColumnAnnotation.element_key.like(f"{prefix}%"))
            ).scalars().all()
            for row in col_rows:
                _, schema_name, table_name, col_name = row.element_key.split("|", 3)
                key = f"{schema_name}.{table_name}"
                entry = annotations.setdefault(key, {})
                col_entry: dict[str, str] = {}
                if row.user_description:
                    col_entry["user_description"] = row.user_description
                if row.mapping_instructions:
                    col_entry["mapping_instructions"] = row.mapping_instructions
                if col_entry:
                    entry.setdefault("columns", {})[col_name] = col_entry

        return {"version": 1, "dataset": dataset_name, "annotations": annotations}

    def save(self, dataset_name: str, data: dict[str, Any]) -> None:
        """Reconcile every table/column row for *dataset_name* against *data*'s current state."""
        ann = data.get("annotations") or {}
        prefix = f"{dataset_name}|"
        now = datetime.now(timezone.utc)

        wanted_tables: dict[str, tuple[str | None, str | None]] = {}
        wanted_cols: dict[str, tuple[str | None, str | None]] = {}
        for key, entry in ann.items():
            schema_name, table_name = _split_table_key(key)
            ud = entry.get("user_description")
            mi = entry.get("mapping_instructions")
            if ud or mi:
                wanted_tables[f"{dataset_name}|{schema_name}|{table_name}"] = (ud, mi)
            for col_name, col_entry in (entry.get("columns") or {}).items():
                col_key = f"{dataset_name}|{schema_name}|{table_name}|{col_name}"
                wanted_cols[col_key] = (col_entry.get("user_description"), col_entry.get("mapping_instructions"))

        with session_scope(self._dsn) as s:
            existing_tables = {
                r.dataset_key: r for r in s.execute(
                    select(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%"))
                ).scalars().all()
            }
            for table_key, (ud, mi) in wanted_tables.items():
                row = existing_tables.pop(table_key, None)
                if row is None:
                    row = CatalogTableAnnotation(dataset_key=table_key)
                    s.add(row)
                row.user_description = ud
                row.mapping_instructions = mi
                row.updated_at = now
            for stale in existing_tables.values():
                s.delete(stale)

            existing_cols = {
                r.element_key: r for r in s.execute(
                    select(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{prefix}%"))
                ).scalars().all()
            }
            for col_key, (ud, mi) in wanted_cols.items():
                row = existing_cols.pop(col_key, None)
                if row is None:
                    row = CatalogColumnAnnotation(element_key=col_key)
                    s.add(row)
                row.user_description = ud
                row.mapping_instructions = mi
                row.updated_at = now
            for stale in existing_cols.values():
                s.delete(stale)

    # ── add-profile-reset: hard delete — annotations have no history table of their own ──

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> dict[str, int]:
        """Delete every table- and column-level annotation for this table.

        Hard delete — annotations have no submission/review workflow or history table of their
        own (matching what ``save()`` already does for anything no longer present in the dict
        it's handed). Takes a caller-managed *session* (D3) — never opens its own transaction.
        Returns ``{"table": 0 or 1, "columns": <count>}``.
        """
        dataset_key = f"{source}|{schema or ''}|{table}"
        element_prefix = f"{dataset_key}|"

        table_row = session.execute(
            select(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key == dataset_key)
        ).scalar_one_or_none()
        cleared_table = 0
        if table_row is not None:
            session.delete(table_row)
            cleared_table = 1

        col_rows = session.execute(
            select(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{element_prefix}%"))
        ).scalars().all()
        for row in col_rows:
            session.delete(row)

        return {"table": cleared_table, "columns": len(col_rows)}

    def clear_for_source(self, session, source: str) -> dict[str, int]:
        """Delete every annotation for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        table_rows = session.execute(
            select(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%"))
        ).scalars().all()
        for row in table_rows:
            session.delete(row)

        col_rows = session.execute(
            select(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{prefix}%"))
        ).scalars().all()
        for row in col_rows:
            session.delete(row)

        return {"table": len(table_rows), "columns": len(col_rows)}
