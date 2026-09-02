"""Postgres-backed repository for element CONTENT (govern-pg-c1-element-content-build).

Mirrors the *content* half of ``core.element_state.ElementStateStore``'s public contract exactly
— ``get_description``/``set_description``, ``get_business_name``/``set_business_name``,
``get_metadata``/``set_metadata``, ``get_data_story``/``set_data_story``,
``get_assessment_scope``/``get_assessment_scope_record``/``set_assessment_scope``.

Explicitly NOT here (the *lifecycle* half): status, submission overlay, review transitions. Those
already branch to Postgres via ``core.element_lifecycle_repo.ElementLifecycleRepo`` and are
untouched by this slice — ``ElementStateStore`` therefore carries two independent backend
switches for a while, which is why they are kept visibly separate.

Adds one method with no YAML equivalent: ``record_submission()`` — opens a real SCD2 window in
``element_definition_history``. Per the C1 decision (2026-08-15) a window opens when the column's
Interpretation Set is SUBMITTED, never on an intermediate save, deliberately mirroring
``SemanticTypeRepo.record_submission()`` so both components of one Interpretation Set version
together.

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.glossary_db.db import session_scope
from core.shared.models import (
    DatasetStory,
    ElementAssessmentScope,
    ElementDefinition,
    ElementDefinitionHistory,
)

#: Must match core.element_state.ASSESSMENT_SCOPE_VALUES / _DEFAULT_ASSESSMENT_SCOPE.
_SCOPE_VALUES = ("in_scope", "out_of_scope")
_DEFAULT_SCOPE = "in_scope"


class ElementContentRepo:
    """Data-access for element/dataset content on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        # Whole-table TTL read caches. The YAML store this replaces served every read from an
        # in-memory dict, so per-call round-trips would be a real regression on the aggregation
        # paths that read content for every column of a source (found live for semantic types,
        # 2026-08-14). Same 2s TTL + invalidate-on-write shape as ElementLifecycleRepo/
        # SemanticTypeRepo.
        self._def_cache: dict[str, dict[str, Any]] | None = None
        self._def_ts: float = 0.0
        self._scope_cache: dict[str, dict[str, Any]] | None = None
        self._scope_ts: float = 0.0
        self._ttl: float = 2.0

    # ── keys (identical shape to ElementStateStore's) ─────────────────────────

    @staticmethod
    def key(source: str, schema: str | None, table: str, column: str) -> str:
        return f"{source}|{schema or ''}|{table}|{column}"

    @staticmethod
    def dataset_key(source: str, schema: str | None, table: str) -> str:
        return f"{source}|{schema or ''}|{table}"

    # ── caches ───────────────────────────────────────────────────────────────

    def _invalidate(self) -> None:
        self._def_cache = None
        self._scope_cache = None

    def _definitions(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if self._def_cache is None or (now - self._def_ts) > self._ttl:
            with session_scope(self._dsn) as s:
                rows = s.execute(select(ElementDefinition)).scalars().all()
            self._def_cache = {
                r.element_key: {
                    "definition": r.definition,
                    "definition_is_ai": r.definition_is_ai,
                    "business_name": r.business_name,
                    "business_name_is_ai": r.business_name_is_ai,
                    "criticality": r.criticality,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            }
            self._def_ts = now
        return self._def_cache

    def all_definitions(self) -> dict[str, dict[str, Any]]:
        """Every element's definition/business-name record, keyed by element_key.

        Public bulk accessor (same TTL cache as every other read here) for the store's
        collection-query methods (``find_in_source``/``get_pending_review``/``search_multi_
        filter``/etc.) — those loop over many keys at once and must not issue one query per
        key, same reasoning as ``SemanticTypeRepo``'s own bulk cache.
        """
        return self._definitions()

    def _scopes(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if self._scope_cache is None or (now - self._scope_ts) > self._ttl:
            with session_scope(self._dsn) as s:
                rows = s.execute(select(ElementAssessmentScope)).scalars().all()
            self._scope_cache = {
                r.element_key: {
                    "scope": r.scope,
                    "scope_reason": r.scope_reason,
                    "scoped_by": r.scoped_by,
                    "scoped_at": r.scoped_at.isoformat() if r.scoped_at else None,
                }
                for r in rows
            }
            self._scope_ts = now
        return self._scope_cache

    def _upsert_definition(self, s, key: str, now: datetime) -> ElementDefinition:
        row = s.execute(
            select(ElementDefinition).where(ElementDefinition.element_key == key).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            row = ElementDefinition(element_key=key, created_at=now, updated_at=now)
            s.add(row)
            s.flush()
        return row

    # ── definition (a.k.a. "description" internally; "Definition" in the UI) ──

    def get_description(self, source: str, schema: str | None, table: str, column: str) -> str | None:
        return self._definitions().get(self.key(source, schema, table, column), {}).get("definition")

    def set_description(self, source: str, schema: str | None, table: str, column: str,
                        description: str, is_ai_generated: bool = False) -> None:
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            row = self._upsert_definition(s, key, now)
            row.definition = description
            row.definition_is_ai = bool(is_ai_generated)
            row.updated_at = now
            s.flush()
        self._invalidate()

    # ── business name ────────────────────────────────────────────────────────

    def get_business_name(self, source: str, schema: str | None, table: str, column: str) -> str | None:
        return self._definitions().get(self.key(source, schema, table, column), {}).get("business_name")

    def set_business_name(self, source: str, schema: str | None, table: str, column: str,
                          name: str, is_ai_generated: bool = False) -> None:
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            row = self._upsert_definition(s, key, now)
            row.business_name = name
            row.business_name_is_ai = bool(is_ai_generated)
            row.updated_at = now
            s.flush()
        self._invalidate()

    # ── metadata ─────────────────────────────────────────────────────────────

    def get_metadata(self, source: str, schema: str | None, table: str, column: str) -> dict:
        """Return the same flat dict shape the YAML store's ``metadata`` section produced.

        Only the keys C1 actually owns are served here — the AI flags, the timestamps, and
        ``criticality``. The legacy ``refdata_*`` keys are NOT returned: reference-code meanings
        moved to the ``reference_code`` table in an earlier slice, and ``refdata_bound_set_id``
        belongs to the reference-sets slice (D) and stays in YAML until then.
        """
        record = self._definitions().get(self.key(source, schema, table, column))
        if not record:
            return {}
        return self._record_to_metadata(record)

    @staticmethod
    def _record_to_metadata(record: dict[str, Any]) -> dict[str, Any]:
        """Shape one ``all_definitions()``/``_definitions()`` record into the YAML metadata dict
        shape. Shared by ``get_metadata`` (single-key) and ``ElementStateStore``'s bulk
        collection-query methods (``find_in_source``/``get_pending_review``/etc.), so both read
        the same fields the same way.
        """
        meta: dict[str, Any] = {
            "is_ai_generated": record["definition_is_ai"],
            "business_name_is_ai": record["business_name_is_ai"],
        }
        for field in ("created_at", "updated_at", "criticality"):
            if record.get(field) is not None:
                meta[field] = record[field]
        return meta

    def set_metadata(self, source: str, schema: str | None, table: str, column: str,
                     metadata: dict) -> None:
        """Apply the C1-owned subset of a metadata update; other keys are ignored.

        The YAML store merged whatever dict it was handed. Here only the fields with a real
        column are written — anything else (notably the reference-data keys owned by other
        slices) is deliberately dropped rather than silently stored in a shape nothing reads.
        """
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            row = self._upsert_definition(s, key, now)
            if "is_ai_generated" in metadata:
                row.definition_is_ai = bool(metadata["is_ai_generated"])
            if "business_name_is_ai" in metadata:
                row.business_name_is_ai = bool(metadata["business_name_is_ai"])
            if "criticality" in metadata:
                row.criticality = metadata["criticality"]
            row.updated_at = now
            s.flush()
        self._invalidate()

    # ── data story (dataset level) ───────────────────────────────────────────

    def get_data_story(self, source: str, schema: str | None, table: str) -> dict | None:
        """Return the YAML store's story shape. ``tagline`` is served from the ``data_grain``
        column so existing callers/UI keep working unchanged while the field has a real name of
        its own in the database (C1 decision, 2026-08-15).
        """
        key = self.dataset_key(source, schema, table)
        with session_scope(self._dsn) as s:
            row = s.execute(
                select(DatasetStory).where(DatasetStory.dataset_key == key)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "tagline": row.data_grain,
                "narrative": row.narrative,
                "is_ai_generated": row.is_ai_generated,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            }

    def set_data_story(self, source: str, schema: str | None, table: str, tagline: str,
                       narrative: str, is_ai_generated: bool = False) -> None:
        key = self.dataset_key(source, schema, table)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            row = s.execute(
                select(DatasetStory).where(DatasetStory.dataset_key == key).with_for_update()
            ).scalar_one_or_none()
            if row is None:
                row = DatasetStory(dataset_key=key, created_at=now)
                s.add(row)
            row.data_grain = tagline
            row.narrative = narrative
            row.is_ai_generated = bool(is_ai_generated)
            row.generated_at = now
            row.updated_at = now
            s.flush()

    # ── assessment scope ─────────────────────────────────────────────────────

    def get_assessment_scope(self, source: str, schema: str | None, table: str, column: str) -> str:
        record = self._scopes().get(self.key(source, schema, table, column))
        return record.get("scope", _DEFAULT_SCOPE) if record else _DEFAULT_SCOPE

    def get_assessment_scope_record(self, source: str, schema: str | None, table: str,
                                    column: str) -> dict:
        record = self._scopes().get(self.key(source, schema, table, column))
        return dict(record) if record else {"scope": _DEFAULT_SCOPE}

    def set_assessment_scope(self, source: str, schema: str | None, table: str, column: str,
                             scope: str, *, scope_reason: str | None = None,
                             scoped_by: str | None = None) -> dict:
        if scope not in _SCOPE_VALUES:
            raise ValueError(f"Invalid assessment scope: {scope!r}")
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            row = s.execute(
                select(ElementAssessmentScope)
                .where(ElementAssessmentScope.element_key == key).with_for_update()
            ).scalar_one_or_none()
            if row is None:
                row = ElementAssessmentScope(element_key=key, created_at=now)
                s.add(row)
            row.scope = scope
            row.scope_reason = scope_reason
            row.scoped_by = scoped_by
            row.scoped_at = now
            row.updated_at = now
            s.flush()
        self._invalidate()
        return {"scope": scope, "scope_reason": scope_reason, "scoped_by": scoped_by,
                "scoped_at": now.isoformat()}

    # ── Interpretation Set submission history (no YAML equivalent) ───────────

    def record_submission(self, source: str, schema: str | None, table: str, column: str, *,
                          submitted_by: str | None = None) -> dict[str, Any]:
        """Open a new history window for this column's definition/business name, closing whichever
        window was previously open.

        The wording is copied straight off the CURRENT row — submission is what makes the wording
        official, so the caller never passes it in. Raises if no content row exists yet: a column
        cannot reach the submit gate without a definition and a business name.
        """
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            current = s.execute(
                select(ElementDefinition).where(ElementDefinition.element_key == key)
            ).scalar_one_or_none()
            if current is None:
                raise ValueError(f"No element_definition found for key {key!r}")

            open_window = s.execute(
                select(ElementDefinitionHistory).where(
                    ElementDefinitionHistory.element_key == key,
                    ElementDefinitionHistory.valid_to.is_(None),
                ).with_for_update()
            ).scalar_one_or_none()
            if open_window is not None:
                open_window.valid_to = now

            row = ElementDefinitionHistory(
                element_definition_id=current.id,
                element_key=key,
                definition=current.definition,
                definition_is_ai=current.definition_is_ai,
                business_name=current.business_name,
                business_name_is_ai=current.business_name_is_ai,
                submitted_by=submitted_by,
                valid_from=now,
            )
            s.add(row)
            s.flush()
            return {
                "element_key": key,
                "definition": row.definition,
                "business_name": row.business_name,
                "submitted_by": row.submitted_by,
                "valid_from": row.valid_from.isoformat(),
                "valid_to": None,
            }

    def history(self, source: str, schema: str | None, table: str, column: str) -> list[dict[str, Any]]:
        """Every recorded wording for this column, oldest window first."""
        key = self.key(source, schema, table, column)
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ElementDefinitionHistory)
                .where(ElementDefinitionHistory.element_key == key)
                .order_by(ElementDefinitionHistory.valid_from)
            ).scalars().all()
            return [
                {
                    "element_key": r.element_key,
                    "definition": r.definition,
                    "definition_is_ai": r.definition_is_ai,
                    "business_name": r.business_name,
                    "business_name_is_ai": r.business_name_is_ai,
                    "submitted_by": r.submitted_by,
                    "valid_from": r.valid_from.isoformat(),
                    "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                }
                for r in rows
            ]

    # ── add-profile-reset: soft-reset content, hard-delete story/scope ──────────

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> dict[str, int]:
        """Reset all content for this table back to its pre-governed default.

        ``ElementDefinition`` (descriptions/business names) is soft-reset (D9): any open
        Interpretation Set submission window in ``element_definition_history`` is closed first,
        then the current row is blanked — nothing is hard-deleted there, mirroring
        ``SemanticTypeRepo.clear_for_table``. ``DatasetStory`` and ``ElementAssessmentScope``
        have no history table of their own (each model's own docstring records that as an
        explicit decision), so they are hard-deleted.

        KNOWN GAP (design.md Risks): a column with an unsubmitted draft definition has no
        history row at all, so this destroys it with nothing to restore from — accepted for
        this change, deferred to tech-debt #4.

        Takes a caller-managed *session* (D3) — never opens its own transaction. Returns
        ``{"definitions": <count>, "story": 0 or 1, "scopes": <count>}``.
        """
        element_prefix = f"{source}|{schema or ''}|{table}|"
        key = self.dataset_key(source, schema, table)
        now = datetime.now(timezone.utc)

        definitions = session.execute(
            select(ElementDefinition)
            .where(ElementDefinition.element_key.like(f"{element_prefix}%"))
            .with_for_update()
        ).scalars().all()
        cleared_defs = 0
        for row in definitions:
            if row.definition is None and row.business_name is None:
                continue   # already blank
            open_window = session.execute(
                select(ElementDefinitionHistory).where(
                    ElementDefinitionHistory.element_key == row.element_key,
                    ElementDefinitionHistory.valid_to.is_(None),
                ).with_for_update()
            ).scalar_one_or_none()
            if open_window is not None:
                open_window.valid_to = now
            row.definition = None
            row.definition_is_ai = False
            row.business_name = None
            row.business_name_is_ai = False
            row.updated_at = now
            cleared_defs += 1

        story = session.execute(
            select(DatasetStory).where(DatasetStory.dataset_key == key)
        ).scalar_one_or_none()
        cleared_story = 0
        if story is not None:
            session.delete(story)
            cleared_story = 1

        scopes = session.execute(
            select(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like(f"{element_prefix}%"))
        ).scalars().all()
        for scope in scopes:
            session.delete(scope)

        if cleared_defs or cleared_story or scopes:
            self._invalidate()
        return {"definitions": cleared_defs, "story": cleared_story, "scopes": len(scopes)}

    def clear_for_source(self, session, source: str) -> dict[str, int]:
        """Reset all content for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        keys = session.execute(
            select(ElementDefinition.element_key).where(ElementDefinition.element_key.like(f"{prefix}%"))
        ).scalars().all()
        tables = {
            (parts[1] or None, parts[2])
            for parts in (k.split("|", 3) for k in keys)
            if len(parts) == 4
        }
        totals = {"definitions": 0, "story": 0, "scopes": 0}
        for schema, table in tables:
            result = self.clear_for_table(session, source, schema, table)
            for field in totals:
                totals[field] += result[field]
        return totals
