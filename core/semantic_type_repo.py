"""Postgres-backed repository for per-column semantic-type assignments (govern-pg-b1-semantic-types-build).

Mirrors ``core.semantic_type_store.SemanticTypeStore``'s public contract exactly (``get()``,
``get_or_default()``, ``get_by_key()``, ``set_record()`` — preserving the ``preserve_disposed``
sticky-disposition rule and the ``latest_proposal`` nesting byte-for-byte — ``set_proposed()``,
``accept()``). No priors read/write (D4 — the learned-
patterns subsystem this would have served was deleted from the codebase, commit ``a74802b``,
before this repo was built).

No persisted disposition ``state`` (retired 2026-08-20 — untangles tech-debt #13/#36/#45): the
only two real, reachable outcomes are the default ``unresolved`` ``type_id`` and an accepted type
(``accepted_at IS NOT NULL``) — there is no Reject action anywhere in the UI, confirmed dead code
with zero callers. ``accept()`` refuses to leave ``type_id`` as ``unresolved`` — an element can
never be accepted without a real governed type.

Adds one new method, ``record_submission()`` — not a mirror of anything in the YAML store. Per
D1, a real SCD2 history row is written into ``semantic_type_assignment_history`` only when an
Interpretation Set is submitted for review, not on every ``accept()``/machine re-resolve. The
history table is self-contained SCD2 (unlike ``dq_score``/``reference_code``'s
separate current+history split): a row's ``valid_from`` is its own submission timestamp,
``valid_to`` stays NULL while it is the most recent submission for that key and is set the
moment a later submission supersedes it.

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.glossary_db.db import session_scope
from core.semantic_type_store import SemanticTypeStore
from core.shared.models import SemanticTypeAssignment, SemanticTypeAssignmentHistory


#: Fields carried on every record dict, in the exact shape SemanticTypeStore returns them.
#: No submitted_at/submitted_by -- a semantic type is never submitted on its own, only as part
#: of the whole Interpretation Set (2026-08-13 user correction).
_RECORD_FIELDS = (
    "type_id", "domain_role", "confidence", "source", "candidates", "evidence",
    "type_value_conflict", "type_datatype_difference", "format", "format_source",
    "format_rationale", "scope", "entity", "pii", "pii_category", "tier", "resolver_version",
    "accepted_by", "accepted_by_role", "accepted_at", "fingerprint",
    "system_deduced_type", "score_breakdown",
)

#: Resolver-written fields whose ABSENCE is meaningful: the widened unresolved path omits the key
#: entirely rather than writing null (semantic_resolver._record_from_signal), and no live record
#: carries either as an explicit null. `latest_proposal` is the same shape from a different writer
#: -- SemanticTypeStore.set_record()'s preserve_disposed branch is the ONLY place that ever adds
#: it, so a fresh/never-disposed record never has the key at all in YAML mode (found live,
#: 2026-08-14: core/semantic_resolver.py's `record.get("latest_proposal", {}).get(...)` crashed
#: with AttributeError on 'NoneType' once postgres mode started returning the key present-but-
#: None instead of genuinely absent). Present in a record dict only when actually set, so a
#: round-trip through Postgres returns the same keys the YAML store would.
_OPTIONAL_RECORD_FIELDS = ("resolution_reason", "nearest_candidates", "latest_proposal")


class SemanticTypeRepo:
    """Data-access for per-column semantic-type assignments on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        # Whole-table TTL read cache (mirrors core/element_lifecycle_repo.py's proven
        # get_status()/all_states() pattern) -- get_by_key() was an individual Postgres
        # round-trip per call (~3.3ms measured, found live 2026-08-14: dominated the Table
        # Overview page's load time, ~1,900 calls for a large table). Same short TTL (2s) as
        # the lifecycle repo, invalidated immediately on any write so edits are never stale.
        self._records_cache: dict[str, dict[str, Any]] | None = None
        self._records_ts: float = 0.0
        self._records_ttl: float = 2.0

    # ── keys (pure, stateless — identical shape to SemanticTypeStore's) ────────

    key = staticmethod(SemanticTypeStore.key)
    split_key = staticmethod(SemanticTypeStore.split_key)
    default_record = staticmethod(SemanticTypeStore.default_record)

    # ── record shape ─────────────────────────────────────────────────────────

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @classmethod
    def _to_record(cls, row: SemanticTypeAssignment) -> dict[str, Any]:
        record: dict[str, Any] = {"key": row.key}
        for field in _RECORD_FIELDS:
            record[field] = getattr(row, field)
        for field in _OPTIONAL_RECORD_FIELDS:
            value = getattr(row, field)
            if value is not None:
                record[field] = value
        record["resolved_at"] = cls._iso(row.resolved_at)
        record["accepted_at"] = cls._iso(row.accepted_at)
        record["updated_at"] = cls._iso(row.updated_at)
        split = cls.split_key(row.key)
        record["column"] = split["column"]
        return record

    @staticmethod
    def _row_kwargs(record: dict[str, Any], now: datetime) -> dict[str, Any]:
        """Build the full set of mapped-column values for a wholesale (non-nested) write —
        mirrors the YAML store's ``next_record = deepcopy(record)`` semantics: every mapped
        field is taken from *record* (defaulting to None/its default), never merged with
        whatever the existing row previously held.
        """
        kwargs: dict[str, Any] = {}
        for field in _RECORD_FIELDS:
            kwargs[field] = record.get(field)
        for field in _OPTIONAL_RECORD_FIELDS:
            kwargs[field] = record.get(field)
        kwargs["confidence"] = max(0.0, min(1.0, float(kwargs["confidence"] or 0.0)))
        kwargs["candidates"] = kwargs["candidates"] or []
        kwargs["evidence"] = kwargs["evidence"] or []
        kwargs["type_value_conflict"] = bool(kwargs["type_value_conflict"])
        kwargs["type_datatype_difference"] = bool(kwargs["type_datatype_difference"])
        kwargs["pii"] = bool(kwargs["pii"])
        kwargs["tier"] = kwargs["tier"] or 0
        kwargs["resolver_version"] = kwargs["resolver_version"] or "1"
        kwargs["resolved_at"] = record.get("resolved_at") or now
        if isinstance(kwargs["resolved_at"], str):
            kwargs["resolved_at"] = datetime.fromisoformat(kwargs["resolved_at"])
        value = kwargs["accepted_at"]
        if isinstance(value, str):
            kwargs["accepted_at"] = datetime.fromisoformat(value)
        return kwargs

    # ── reads ────────────────────────────────────────────────────────────────

    def get(self, source: str, schema: str | None, table: str, column: str) -> dict[str, Any] | None:
        return self.get_by_key(self.key(source, schema, table, column))

    def _refresh_records_cache(self) -> dict[str, dict[str, Any]]:
        """One bulk query for every row in the table -- refreshed at most once per
        ``_records_ttl`` seconds (or immediately after any write, via ``_invalidate_cache``).
        """
        with session_scope(self._dsn) as s:
            rows = s.execute(select(SemanticTypeAssignment)).scalars().all()
        self._records_cache = {row.key: self._to_record(row) for row in rows}
        self._records_ts = time.monotonic()
        return self._records_cache

    def _invalidate_cache(self) -> None:
        self._records_cache = None

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        if self._records_cache is None or (now - self._records_ts) > self._records_ttl:
            self._refresh_records_cache()
        record = self._records_cache.get(key)
        return dict(record) if record is not None else None

    def get_or_default(self, source: str, schema: str | None, table: str, column: str) -> dict[str, Any]:
        record = self.get(source, schema, table, column) or self.default_record(
            source=source, schema=schema, table=table, column=column
        )
        record.setdefault("column", column)
        return record

    def domain_roles_for_source(self, source: str) -> dict[str, str]:
        """One bulk query: every column's ``domain_role`` for this source, keyed by the full
        ``source|schema|table|column`` key. Built for the Source Profile page's semantic-type
        chart, which previously called ``get()`` once per column (up to ~1,900 individual
        round-trips for a large source, found live 2026-08-14 -- ~3.3ms/call, ~90% of that
        page's load time). A single query transferring ~1,900 small (key, domain_role) pairs
        costs a small fraction of that -- the round-trip COUNT was the real cost, not the data
        volume. Columns with no row at all (never resolved) are simply absent from the
        returned dict -- the caller falls back to its existing heuristic for those, exactly as
        the per-column path already does.
        """
        prefix = f"{source}|"
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(SemanticTypeAssignment.key, SemanticTypeAssignment.domain_role)
                .where(SemanticTypeAssignment.key.like(f"{prefix}%"))
            ).all()
        return {key: domain_role for key, domain_role in rows}

    def semantic_states_for_source(self, source: str) -> dict[str, int]:
        """One bulk query: how many of this source's columns are accepted / pending /
        unresolved. Mirrors ``domain_roles_for_source``'s single-round-trip approach for the
        same reason (the round-trip COUNT is the cost, not the data volume). Counts only
        columns that have a row; callers add never-resolved columns to ``unresolved``
        themselves, since this repo has no view of the catalog's full column list.
        """
        prefix = f"{source}|"
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(SemanticTypeAssignment.type_id, SemanticTypeAssignment.accepted_at)
                .where(SemanticTypeAssignment.key.like(f"{prefix}%"))
            ).all()
        counts = {"accepted": 0, "pending": 0, "unresolved": 0}
        for type_id, accepted_at in rows:
            if not type_id or type_id == "unresolved":
                counts["unresolved"] += 1
            elif accepted_at is not None:
                counts["accepted"] += 1
            else:
                counts["pending"] += 1
        return counts

    def find_in_source(self, source: str) -> list[dict[str, Any]]:
        prefix = f"{source}|"
        if self._records_cache is None or (time.monotonic() - self._records_ts) > self._records_ttl:
            self._refresh_records_cache()
        return [dict(record) for key, record in self._records_cache.items() if key.startswith(prefix)]

    def find_table(self, source: str, schema: str | None, table: str) -> list[dict[str, Any]]:
        prefix = f"{source}|{schema or ''}|{table}|"
        if self._records_cache is None or (time.monotonic() - self._records_ts) > self._records_ttl:
            self._refresh_records_cache()
        return [dict(record) for key, record in self._records_cache.items() if key.startswith(prefix)]

    # ── writes ───────────────────────────────────────────────────────────────

    def set_record(self, record: dict[str, Any], *, preserve_disposed: bool = True) -> dict[str, Any]:
        key = str(record.get("key") or "")
        if not key:
            raise ValueError("Semantic type record missing key")

        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            existing = s.execute(
                select(SemanticTypeAssignment).where(SemanticTypeAssignment.key == key).with_for_update()
            ).scalar_one_or_none()

            if preserve_disposed and existing is not None and existing.accepted_at is not None:
                # SD-R4: refresh only the fingerprint (bookkeeping about which evidence was
                # last looked at, not part of the steward's decision) and park the fresh
                # proposal under latest_proposal — the steward's decision is never overwritten.
                existing.latest_proposal = record
                existing.fingerprint = record.get("fingerprint")
                existing.updated_at = now
                s.flush()
                self._invalidate_cache()
                return self._to_record(existing)

            kwargs = self._row_kwargs(record, now)
            if existing is None:
                row = SemanticTypeAssignment(key=key, **kwargs)
                s.add(row)
                s.flush()
                self._invalidate_cache()
                return self._to_record(row)

            for field, value in kwargs.items():
                setattr(existing, field, value)
            existing.updated_at = now
            s.flush()
            self._invalidate_cache()
            return self._to_record(existing)

    def set_proposed(
        self,
        *,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        type_id: str,
        domain_role: str,
        confidence: float,
        candidates: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        resolver_source: str = "rule",
        type_value_conflict: bool = False,
        type_datatype_difference: bool = False,
        format: str | None = None,
        format_source: str | None = None,
        format_rationale: str | None = None,
        scope: str | None = None,
        entity: str | None = None,
        pii: bool = False,
        pii_category: str | None = None,
        fingerprint: str | None = None,
        resolver_version: str = "1",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "key": self.key(source, schema, table, column),
            "type_id": type_id,
            "domain_role": domain_role,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "source": resolver_source,
            "candidates": candidates or [],
            "evidence": evidence or [],
            "type_value_conflict": bool(type_value_conflict),
            "type_datatype_difference": bool(type_datatype_difference),
            "format": format,
            "format_source": format_source,
            "format_rationale": format_rationale,
            "scope": scope,
            "entity": entity,
            "pii": pii,
            "pii_category": pii_category,
            "resolver_version": resolver_version,
            "resolved_at": now,
            "fingerprint": fingerprint,
        }
        return self.set_record(record, preserve_disposed=True)

    def accept(
        self,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        *,
        accepted_by: str | None = None,
        accepted_by_role: str | None = None,
        type_id: str | None = None,
        domain_role: str | None = None,
    ) -> dict[str, Any]:
        """Accept the current (or a steward-replaced) semantic type for this column.

        Refuses to leave ``type_id`` as ``unresolved`` -- an element can never be accepted
        without a real governed type (2026-08-20, closes a previously unenforced gap: the UI
        only ever hides the Accept button for an unresolved column, this makes it a real rule).
        """
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            existing = s.execute(
                select(SemanticTypeAssignment).where(SemanticTypeAssignment.key == key).with_for_update()
            ).scalar_one_or_none()
            if existing is None:
                default = self.default_record(source=source, schema=schema, table=table, column=column)
                existing = SemanticTypeAssignment(key=key, **self._row_kwargs(default, now))
                s.add(existing)
                s.flush()
            if type_id and type_id != existing.type_id and not existing.system_deduced_type:
                # First-ever override: preserve the machine's own suggestion before it's
                # overwritten below (B1 D1 fix — was previously lost with no recovery path).
                existing.system_deduced_type = {
                    "type_id": existing.type_id,
                    "domain_role": existing.domain_role,
                    "confidence": existing.confidence,
                }
            if type_id:
                existing.type_id = type_id
            if domain_role:
                existing.domain_role = domain_role
            if not existing.type_id or existing.type_id == "unresolved":
                raise ValueError("Cannot accept a column with no resolved semantic type — pick one first.")
            existing.accepted_by = accepted_by
            existing.accepted_by_role = accepted_by_role
            existing.accepted_at = now
            existing.updated_at = now
            s.flush()
            self._invalidate_cache()
            return self._to_record(existing)

    # ── Interpretation Set submission history (D1, new — no YAML equivalent) ──

    @staticmethod
    def _history_to_dict(row: SemanticTypeAssignmentHistory) -> dict[str, Any]:
        return {
            "key": row.key,
            "type_id": row.type_id,
            "domain_role": row.domain_role,
            "confidence": row.confidence,
            "source": row.source,
            "candidates": row.candidates,
            "evidence": row.evidence,
            "type_value_conflict": row.type_value_conflict,
            "type_datatype_difference": row.type_datatype_difference,
            "format": row.format,
            "format_source": row.format_source,
            "format_rationale": row.format_rationale,
            "scope": row.scope,
            "entity": row.entity,
            "pii": row.pii,
            "pii_category": row.pii_category,
            "tier": row.tier,
            "resolver_version": row.resolver_version,
            "accepted_by": row.accepted_by,
            "accepted_by_role": row.accepted_by_role,
            "accepted_at": SemanticTypeRepo._iso(row.accepted_at),
            "fingerprint": row.fingerprint,
            "deduced_type_id": row.deduced_type_id,
            "deduced_domain_role": row.deduced_domain_role,
            "deduced_confidence": row.deduced_confidence,
            "deduced_tier": row.deduced_tier,
            "deduced_resolver_version": row.deduced_resolver_version,
            "submitted_by": row.submitted_by,
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
        }

    def record_submission(
        self,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        *,
        deduced_type_id: str,
        deduced_domain_role: str | None = None,
        deduced_confidence: float | None = None,
        deduced_tier: int | None = None,
        deduced_resolver_version: str | None = None,
        submitted_by: str | None = None,
    ) -> dict[str, Any]:
        """Open a new SCD2 window in ``semantic_type_assignment_history`` for this submission,
        closing whichever window (if any) was previously open for this key.

        The full "accepted" snapshot (type_id/domain_role/confidence/... -- everything a
        person actually accepted) is copied directly from the CURRENT ``semantic_type_assignment``
        row, since submission can only happen once that row is accepted. Only the ``deduced_*``
        fields (what the machine's own resolver independently believes right now, which can
        differ from the accepted snapshot when a steward overrode it) are supplied by the caller.

        Raises if no ``semantic_type_assignment`` row exists yet for this key -- a column must
        already have been resolved before it can reach the Interpretation Set submit gate.
        """
        key = self.key(source, schema, table, column)
        now = datetime.now(timezone.utc)
        with session_scope(self._dsn) as s:
            current = s.execute(
                select(SemanticTypeAssignment).where(SemanticTypeAssignment.key == key)
            ).scalar_one_or_none()
            if current is None:
                raise ValueError(f"No semantic_type_assignment found for key {key!r}")

            open_window = s.execute(
                select(SemanticTypeAssignmentHistory).where(
                    SemanticTypeAssignmentHistory.key == key,
                    SemanticTypeAssignmentHistory.valid_to.is_(None),
                ).with_for_update()
            ).scalar_one_or_none()
            if open_window is not None:
                open_window.valid_to = now

            history_row = SemanticTypeAssignmentHistory(
                semantic_type_assignment_id=current.id,
                key=key,
                # Full accepted snapshot, copied straight from the current row.
                type_id=current.type_id, domain_role=current.domain_role,
                confidence=current.confidence, source=current.source,
                candidates=current.candidates, evidence=current.evidence,
                type_value_conflict=current.type_value_conflict,
                type_datatype_difference=current.type_datatype_difference,
                format=current.format, format_source=current.format_source,
                format_rationale=current.format_rationale, scope=current.scope,
                entity=current.entity, pii=current.pii, pii_category=current.pii_category,
                tier=current.tier, resolver_version=current.resolver_version,
                accepted_by=current.accepted_by, accepted_by_role=current.accepted_by_role,
                accepted_at=current.accepted_at, fingerprint=current.fingerprint,
                # The machine's own, independent opinion right now.
                deduced_type_id=deduced_type_id, deduced_domain_role=deduced_domain_role,
                deduced_confidence=deduced_confidence, deduced_tier=deduced_tier,
                deduced_resolver_version=deduced_resolver_version,
                submitted_by=submitted_by, valid_from=now, valid_to=None,
            )
            s.add(history_row)
            s.flush()
            return self._history_to_dict(history_row)

    # ── add-profile-reset: soft-reset (D9) — never opens its own transaction ────

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> int:
        """Soft-reset every column's semantic-type assignment for this table.

        Closes any open Interpretation Set submission window into
        ``semantic_type_assignment_history`` (mirrors ``record_submission``'s own
        window-closing step — a reset supersedes whatever was open, exactly like a later
        submission would), then blanks the current row back to its unresolved default.
        Nothing is hard-deleted (D9): the history rows this closes stay exactly where they are.

        Takes a caller-managed *session* (D3) — unlike every other public method on this class,
        this never opens its own ``session_scope()``, so the reset orchestrator can wrap it in
        one shared transaction with every other store's clear. Returns the number of columns
        actually cleared (already-blank rows are skipped, keeping repeated calls idempotent).
        """
        prefix = f"{source}|{schema or ''}|{table}|"
        now = datetime.now(timezone.utc)
        rows = session.execute(
            select(SemanticTypeAssignment)
            .where(SemanticTypeAssignment.key.like(f"{prefix}%"))
            .with_for_update()
        ).scalars().all()

        cleared = 0
        for row in rows:
            split = self.split_key(row.key)
            default = self.default_record(
                source=split["source"], schema=split["schema"] or None,
                table=split["table"], column=split["column"],
            )
            already_blank = (
                row.type_id == default["type_id"] and row.accepted_at is None
                and row.confidence == default["confidence"] and not row.system_deduced_type
            )
            if already_blank:
                continue

            open_window = session.execute(
                select(SemanticTypeAssignmentHistory).where(
                    SemanticTypeAssignmentHistory.key == row.key,
                    SemanticTypeAssignmentHistory.valid_to.is_(None),
                ).with_for_update()
            ).scalar_one_or_none()
            if open_window is not None:
                open_window.valid_to = now

            # Reuse the same normalization set_record()'s update branch applies (tier's
            # NOT NULL default, resolver_version's default, confidence clamping, etc.) rather
            # than copying default_record()'s dict fields raw.
            for field, value in self._row_kwargs(default, now).items():
                setattr(row, field, value)
            for field in _OPTIONAL_RECORD_FIELDS:
                setattr(row, field, None)
            row.updated_at = now
            cleared += 1

        if cleared:
            self._invalidate_cache()
        return cleared

    def clear_for_source(self, session, source: str) -> int:
        """Soft-reset every semantic-type assignment for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        rows = session.execute(
            select(SemanticTypeAssignment.key).where(SemanticTypeAssignment.key.like(f"{prefix}%"))
        ).scalars().all()
        tables = {
            (split["schema"] or None, split["table"])
            for split in (self.split_key(k) for k in rows)
        }
        return sum(self.clear_for_table(session, source, schema, table) for schema, table in tables)
