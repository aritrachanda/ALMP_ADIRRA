"""Postgres-backed repository for shared reference sets (govern-pg-d-reference-sets).

Mirrors ``core.reference_set_store.ReferenceSetStore``'s read contract exactly --
``list()``/``get()``/``meanings()``/``values()`` return the identical flat-dict shape the YAML
store already produced.

Adds the column-to-set BINDING methods with no YAML-store equivalent on this class (the legacy
binding lived as a bare ``refdata_bound_set_id`` note inside ``element_states.yaml``'s
``metadata``, read/written by ``ElementStateStore.get_reference_binding``/
``set_reference_binding``/``clear_reference_binding`` -- those now branch to this repo too, see
``core/element_state.py``).

Sets/entries are hand-authored and effectively static this slice (no in-app editing surface —
see the module docstring's "explicitly NOT included" note in the 0015 migration), so a single
whole-table load is cached indefinitely per instance, refreshed only if ``invalidate()`` is
called. The BINDING table, by contrast, is genuinely written through the app today, so it gets
the same short-TTL, invalidate-on-write cache shape used by every other Postgres-backed store
here (``SemanticTypeRepo``/``ElementLifecycleRepo``/etc.).

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.glossary_db.db import session_scope
from core.shared.models import ElementReferenceBinding, ReferenceSet, ReferenceSetEntry


def _entry_dict(row: ReferenceSetEntry) -> dict[str, Any]:
    return {
        "code": row.code,
        "value": row.value,
        "meaning": row.meaning,
        "status": row.status,
        "aliases": row.aliases or [],
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
    }


class ReferenceSetRepo:
    """Data-access for shared reference sets + the column-to-set binding, on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        self._sets_cache: dict[str, dict[str, Any]] | None = None
        self._binding_cache: dict[str, str] | None = None
        self._binding_ts: float = 0.0
        self._binding_ttl: float = 2.0

    # ── sets + entries (static this slice — no write path, no TTL needed) ────

    def invalidate(self) -> None:
        """Drop the cached sets/entries — only needed if a future slice adds set editing."""
        self._sets_cache = None

    def _sets(self) -> dict[str, dict[str, Any]]:
        if self._sets_cache is None:
            with session_scope(self._dsn) as s:
                sets = s.execute(select(ReferenceSet)).scalars().all()
                by_pk_id = {row.id: row for row in sets}
                entries = s.execute(select(ReferenceSetEntry)).scalars().all()
            entries_by_set: dict[int, list[ReferenceSetEntry]] = {}
            for e in entries:
                entries_by_set.setdefault(e.reference_set_id, []).append(e)
            cache: dict[str, dict[str, Any]] = {}
            for row in sets:
                parent = by_pk_id.get(row.parent_set_id) if row.parent_set_id else None
                cache[row.set_id] = {
                    "id": row.set_id,
                    "name": row.name,
                    "kind": row.kind,
                    "standard_ref": row.standard_ref,
                    "status": row.status,
                    "parent_set_id": parent.set_id if parent else None,
                    "entries": [
                        _entry_dict(e)
                        for e in sorted(entries_by_set.get(row.id, []), key=lambda e: e.code)
                    ],
                }
            self._sets_cache = cache
        return self._sets_cache

    def list(self) -> list[dict[str, Any]]:
        """Return all sets (deep-copied) sorted by name."""
        return deepcopy(sorted(self._sets().values(), key=lambda s: str(s["name"]).lower()))

    def get(self, set_id: str) -> dict[str, Any] | None:
        """Return one set by id (deep-copied), or ``None`` if unknown."""
        found = self._sets().get(set_id)
        return deepcopy(found) if found is not None else None

    def meanings(self, set_id: str) -> dict[str, str]:
        """Return ``{code: meaning}`` for a set's entries, or ``{}`` if unknown."""
        found = self._sets().get(set_id)
        if not found:
            return {}
        return {e["code"]: e["meaning"] for e in found["entries"] if e.get("meaning") is not None}

    def values(self, set_id: str) -> dict[str, str]:
        """Return ``{code: value}`` for a set's entries, or ``{}`` if unknown."""
        found = self._sets().get(set_id)
        if not found:
            return {}
        return {e["code"]: e["value"] for e in found["entries"] if e.get("value") is not None}

    # ── column-to-set binding (real write path, TTL cache like every other repo) ─

    def _invalidate_bindings(self) -> None:
        self._binding_cache = None

    def _bindings(self) -> dict[str, str]:
        now = time.monotonic()
        if self._binding_cache is None or (now - self._binding_ts) > self._binding_ttl:
            with session_scope(self._dsn) as s:
                rows = s.execute(
                    select(ElementReferenceBinding.element_key, ReferenceSet.set_id)
                    .join(ReferenceSet, ReferenceSet.id == ElementReferenceBinding.bound_set_id)
                ).all()
            self._binding_cache = {key: set_id for key, set_id in rows}
            self._binding_ts = now
        return self._binding_cache

    def get_binding(self, element_key: str) -> str | None:
        return self._bindings().get(element_key)

    def bindings_for_source(self, source: str | None = None) -> dict[str, str]:
        """``{element_key: set_id}`` for every bound column, optionally one source only."""
        all_bindings = self._bindings()
        if not source:
            return dict(all_bindings)
        prefix = f"{source}|"
        return {k: v for k, v in all_bindings.items() if k.startswith(prefix)}

    def set_binding(self, element_key: str, set_id: str) -> None:
        """Bind a column to a reference set. Raises ``ValueError`` if the set is unknown."""
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            target = s.execute(
                select(ReferenceSet).where(ReferenceSet.set_id == set_id)
            ).scalar_one_or_none()
            if target is None:
                raise ValueError(f"Unknown reference set: {set_id!r}")
            row = s.execute(
                select(ElementReferenceBinding)
                .where(ElementReferenceBinding.element_key == element_key).with_for_update()
            ).scalar_one_or_none()
            if row is None:
                row = ElementReferenceBinding(element_key=element_key, created_at=now)
                s.add(row)
            row.bound_set_id = target.id
            row.updated_at = now
            s.flush()
        self._invalidate_bindings()

    def clear_binding(self, element_key: str) -> None:
        with session_scope(self._dsn) as s:
            row = s.execute(
                select(ElementReferenceBinding)
                .where(ElementReferenceBinding.element_key == element_key).with_for_update()
            ).scalar_one_or_none()
            if row is not None:
                s.delete(row)
        self._invalidate_bindings()

    # ── add-profile-reset: hard delete — no history table exists for bindings ───

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> int:
        """Delete every column's reference-set binding for this table.

        Bindings have no history table of their own (only the binding REVIEW lifecycle does,
        see ``ReferenceBindingReviewRepo``), so this is a hard delete — the same shape
        ``clear_binding`` already uses, just against the caller's *session* (D3) instead of
        opening its own ``session_scope()``. Returns the number of bindings removed.
        """
        prefix = f"{source}|{schema or ''}|{table}|"
        rows = session.execute(
            select(ElementReferenceBinding)
            .where(ElementReferenceBinding.element_key.like(f"{prefix}%"))
            .with_for_update()
        ).scalars().all()
        for row in rows:
            session.delete(row)
        if rows:
            self._invalidate_bindings()
        return len(rows)

    def clear_for_source(self, session, source: str) -> int:
        """Delete every reference-set binding for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        rows = session.execute(
            select(ElementReferenceBinding)
            .where(ElementReferenceBinding.element_key.like(f"{prefix}%"))
            .with_for_update()
        ).scalars().all()
        for row in rows:
            session.delete(row)
        if rows:
            self._invalidate_bindings()
        return len(rows)

