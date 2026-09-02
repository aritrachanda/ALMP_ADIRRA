"""Postgres-backed store for per-code Reference Data (Phase 5b.2).

Reference Data becomes a per-code reviewable object: each distinct code in a coded column
is its own row (``reference_code``) carrying Value / Meaning / Origin / Status, reviewed and
frozen *per code* rather than whole-tab. This is the first governance slice built DIRECTLY on
Postgres (behind the ``database.refdata_backend`` flag, default ``yaml``).

Scope for 5b.2: Save draft (empty → draft) and partial Submit (draft → in_review). Per-code
Approve arrives via the Review Workspace queue in 5b.3; approved rows (seeded by the migration
of already-approved fields) are frozen. In-review rows are locked pending review (Withdraw is
5b.3). Only ``empty`` / ``draft`` rows are editable in the asset tab.

Per-code lifecycle events reuse the generic ``lifecycle_transition`` table
(``subject_type='reference_code'``, ``subject_ref='<element_key>|<code>'``).

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.glossary_db.db import session_scope
from core.shared.models import LifecycleTransition, ReferenceCode, ReferenceCodeHistory
from core.lifecycle_vocab import REVOKED, WITHDRAWN

_ROOT = Path(__file__).resolve().parents[1]

SUBJECT_TYPE = "reference_code"

#: Business-effective sentinel for a code's first-ever approved version (historize-reference-
#: codes D2) — its true origin predates ADIRRA tracking it, so no real date is claimed.
_VALID_FROM_SENTINEL = datetime(1800, 1, 1, tzinfo=timezone.utc)

#: Per-code lifecycle vocabulary (shared canonical set — see core.lifecycle_vocab).
CODE_STATUSES: tuple[str, ...] = ("empty", "draft", "in_review", "approved", "returned", "rejected")
#: Statuses a steward can still edit in the asset tab (in_review/approved are locked).
EDITABLE_STATUSES = frozenset({"empty", "draft"})
#: Statuses that count as "documented content present" for the set-level rollup + DQ.
CONTENT_STATUSES = frozenset({"draft", "in_review", "approved"})

_ORIGINS = frozenset({"profiled", "declared"})
_DEFAULT_ORIGIN = "profiled"

#: Cache of the project.yaml refdata_backend value (does not change without a restart).
_PROJECT_BACKEND_CACHE: str | None = None


def refdata_backend() -> str:
    """Return the configured reference-data backend: 'yaml' (default) or 'postgres'.

    ``ADIRRA_REFDATA_BACKEND`` env var wins (live, per-call — used by tests). Otherwise the
    ``project.yaml`` ``database.refdata_backend`` value is read once and cached.
    """
    env = os.environ.get("ADIRRA_REFDATA_BACKEND")
    if env:
        return env.strip().lower()
    global _PROJECT_BACKEND_CACHE
    if _PROJECT_BACKEND_CACHE is None:
        try:
            with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
                db = (yaml.safe_load(fh) or {}).get("database", {}) or {}
            _PROJECT_BACKEND_CACHE = str(db.get("refdata_backend", "yaml")).strip().lower()
        except Exception:
            _PROJECT_BACKEND_CACHE = "yaml"
    return _PROJECT_BACKEND_CACHE


def make_key(source: str, schema: str | None, table: str, column: str) -> str:
    """The reference-data element key — identical shape to ``ElementStateStore.key``."""
    return f"{source}|{schema or ''}|{table}|{column}"


def derive_set_status(rows: list[dict[str, Any]]) -> str:
    """Roll per-code statuses up to the single DQ-facing status.

    ``approved`` only when every documented code is approved (value-preserving vs the legacy
    whole-field ``refdata_status``); else ``under_review`` if any documented code is in review;
    else ``candidate`` if anything is documented; else ``none``.
    """
    documented = [r for r in rows if str(r.get("meaning") or "").strip()]
    if not documented:
        return "none"
    if all(r.get("status") == "approved" for r in documented):
        return "approved"
    if any(r.get("status") == "in_review" for r in documented):
        return "under_review"
    return "candidate"


def set_badge(rows: list[dict[str, Any]]) -> str:
    """Display badge for the whole tab: partially-approved until 100% approved."""
    applicable = [r for r in rows if r.get("status") in CONTENT_STATUSES]
    if not applicable:
        return "empty"
    approved = sum(r.get("status") == "approved" for r in applicable)
    if approved and approved == len(applicable):
        return "approved"
    if approved:
        return "partially_approved"
    if any(r.get("status") == "in_review" for r in applicable):
        return "in_review"
    return "draft"


def _row_dict(row: ReferenceCode) -> dict[str, Any]:
    return {
        "code": row.code,
        "value": row.value,
        "meaning": row.meaning,
        "origin": row.origin,
        "status": row.status,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "submitted_by": row.submitted_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "approved_by": row.approved_by,
    }


class ReferenceCodeRepo:
    """Data-access for per-code Reference Data on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        # Short-TTL batched cache of the whole {element_key: {codes_documented, status}} map,
        # for the DQ hot path + Reference Dataspace overview (called once per column in loops).
        self._summary_cache: dict[str, dict[str, Any]] | None = None
        self._summary_ts: float = 0.0
        self._summary_ttl: float = 2.0

    # ── reads ────────────────────────────────────────────────────────────────
    def get_codes(self, element_key: str) -> list[dict[str, Any]]:
        """Return all stored code rows for a column (empty list if none stored yet)."""
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key)
                .order_by(ReferenceCode.code)
            ).scalars().all()
            return [_row_dict(r) for r in rows]

    def published_register(self, source: str | None = None) -> list[dict[str, Any]]:
        """Codesets for the Reference Dataspace register: each coded column's PUBLISHED
        codes (``in_review`` + ``approved`` only). A codeset appears only if it has at
        least one such code. Optional ``source`` filters on the element_key prefix.

        Returns ``[{element_key, codes: [_row_dict, ...]}]`` ordered by key then code.
        """
        published = ("in_review", "approved")
        by_key: dict[str, list[dict[str, Any]]] = {}
        with session_scope(self._dsn) as s:
            stmt = select(ReferenceCode).where(ReferenceCode.status.in_(published))
            if source:
                stmt = stmt.where(ReferenceCode.element_key.like(f"{source}|%"))
            stmt = stmt.order_by(ReferenceCode.element_key, ReferenceCode.code)
            for r in s.execute(stmt).scalars().all():
                by_key.setdefault(r.element_key, []).append(_row_dict(r))
        return [{"element_key": key, "codes": rows} for key, rows in by_key.items()]

    def summary(self, element_key: str) -> dict[str, Any]:
        """DQ-facing summary for one column: codes_documented + derived set status."""
        return self._summaries().get(
            element_key, {"codes_documented": 0, "status": "none"}
        )

    def _summaries(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if self._summary_cache is None or (now - self._summary_ts) > self._summary_ttl:
            self._summary_cache = self._build_summaries()
            self._summary_ts = now
        return self._summary_cache

    def _build_summaries(self) -> dict[str, dict[str, Any]]:
        by_key: dict[str, list[dict[str, Any]]] = {}
        with session_scope(self._dsn) as s:
            rows = s.execute(select(ReferenceCode)).scalars().all()
            for r in rows:
                by_key.setdefault(r.element_key, []).append(_row_dict(r))
        return {
            key: {
                "codes_documented": sum(1 for r in rows if str(r.get("meaning") or "").strip()),
                "status": derive_set_status(rows),
            }
            for key, rows in by_key.items()
        }

    # ── writes (each = one transaction) ──────────────────────────────────────
    def save_codes(self, element_key: str, edits: list[dict[str, Any]], *,
                   actor: str | None = None, actor_role: str | None = None) -> list[dict[str, Any]]:
        """Upsert draft edits for a set of codes (Save draft).

        Each edit is ``{code, value?, meaning?, origin?}``. An empty code that gains content
        moves to ``draft``; ``in_review`` / ``approved`` codes are locked and skipped. Returns
        the full, refreshed code list.
        """
        with session_scope(self._dsn) as s:
            for edit in edits:
                code = str(edit.get("code"))
                if not code:
                    continue
                origin = str(edit.get("origin") or _DEFAULT_ORIGIN).lower()
                if origin not in _ORIGINS:
                    origin = _DEFAULT_ORIGIN
                row = s.execute(
                    select(ReferenceCode)
                    .where(ReferenceCode.element_key == element_key,
                           ReferenceCode.code == code)
                    .with_for_update()
                ).scalar_one_or_none()
                if row is None:
                    s.execute(
                        pg_insert(ReferenceCode.__table__)
                        .values(element_key=element_key, code=code, status="empty",
                                origin=origin)
                        .on_conflict_do_nothing(index_elements=["element_key", "code"])
                    )
                    row = s.execute(
                        select(ReferenceCode)
                        .where(ReferenceCode.element_key == element_key,
                               ReferenceCode.code == code)
                        .with_for_update()
                    ).scalar_one()
                if row.status not in EDITABLE_STATUSES:
                    continue  # in_review / approved are locked
                if "value" in edit:
                    row.value = edit.get("value") or None
                if "meaning" in edit:
                    row.meaning = edit.get("meaning") or None
                if "origin" in edit:
                    row.origin = origin
                from_status = row.status
                has_content = bool(str(row.value or "").strip() or str(row.meaning or "").strip())
                row.status = "draft" if has_content else "empty"
                row.updated_at = func.now()
                if row.status != from_status:
                    s.add(LifecycleTransition(
                        subject_type=SUBJECT_TYPE,
                        subject_ref=f"{element_key}|{code}",
                        from_status=from_status, to_status=row.status,
                        actor=actor, actor_role=actor_role, reason="save draft",
                    ))
        self._summary_cache = None
        return self.get_codes(element_key)

    def submit_codes(self, element_key: str, codes: list[str] | None = None, *,
                     actor: str | None = None, actor_role: str | None = None) -> dict[str, Any]:
        """Partial Submit: move filled ``draft`` codes to ``in_review``.

        ``codes`` limits the submission to those code values; ``None`` submits every eligible
        draft. Only rows with content (a meaning) are submitted. Returns ``{submitted, codes}``.
        """
        wanted = {str(c) for c in codes} if codes is not None else None
        submitted: list[str] = []
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key,
                       ReferenceCode.status == "draft")
                .with_for_update()
            ).scalars().all()
            for row in rows:
                if wanted is not None and row.code not in wanted:
                    continue
                if not str(row.meaning or "").strip():
                    continue  # only filled codes are submittable
                row.status = "in_review"
                row.submitted_at = func.now()
                row.submitted_by = actor
                row.updated_at = func.now()
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE,
                    subject_ref=f"{element_key}|{row.code}",
                    from_status="draft", to_status="in_review",
                    actor=actor, actor_role=actor_role, reason="submit for review",
                ))
                submitted.append(row.code)
        self._summary_cache = None
        return {"submitted": len(submitted), "codes": submitted}

    def withdraw_codes(self, element_key: str, codes: list[str], *,
                       actor: str | None = None, actor_role: str | None = None) -> dict[str, Any]:
        """Analyst pulls submitted codes back: ``in_review`` → editable ``draft`` (5b.3.1).

        Only rows currently ``in_review`` among ``codes`` are affected. The audit trail records
        the transition-only ``withdrawn`` action (see core.lifecycle_vocab); the row rests in
        ``draft``. Returns ``{withdrawn, codes}``.
        """
        wanted = {str(c) for c in codes}
        withdrawn: list[str] = []
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key,
                       ReferenceCode.status == "in_review")
                .with_for_update()
            ).scalars().all()
            for row in rows:
                if row.code not in wanted:
                    continue
                row.status = "draft"
                row.submitted_at = None
                row.submitted_by = None
                row.updated_at = func.now()
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE,
                    subject_ref=f"{element_key}|{row.code}",
                    from_status="in_review", to_status=WITHDRAWN,
                    actor=actor, actor_role=actor_role, reason="withdraw",
                ))
                withdrawn.append(row.code)
        self._summary_cache = None
        return {"withdrawn": len(withdrawn), "codes": withdrawn}

    def revoke_codes(self, element_key: str, codes: list[str], *,
                     actor: str | None = None, actor_role: str | None = None) -> dict[str, Any]:
        """Analyst pulls approved codes back: ``approved`` → editable ``draft`` (5b.3.1).

        Only rows currently ``approved`` among ``codes`` are affected. The audit trail records
        the transition-only ``revoked`` action (see core.lifecycle_vocab); the row rests in
        ``draft``. Returns ``{revoked, codes}``.

        Also closes the outgoing version into ``reference_code_history`` (historize-reference-
        codes) with a real ``valid_to`` = this revoke's timestamp — this is what creates the gap
        a point-in-time lookup must honestly report as "not approved" rather than silently
        extending the old value's validity through a period it wasn't actually approved.
        """
        wanted = {str(c) for c in codes}
        revoked: list[str] = []
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key,
                       ReferenceCode.status == "approved")
                .with_for_update()
            ).scalars().all()
            for row in rows:
                if row.code not in wanted:
                    continue
                self._close_current_into_history(s, row, valid_to=func.now())
                row.status = "draft"
                row.approved_at = None
                row.approved_by = None
                row.submitted_at = None
                row.submitted_by = None
                row.updated_at = func.now()
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE,
                    subject_ref=f"{element_key}|{row.code}",
                    from_status="approved", to_status=REVOKED,
                    actor=actor, actor_role=actor_role, reason="revoke",
                ))
                revoked.append(row.code)
        self._summary_cache = None
        return {"revoked": len(revoked), "codes": revoked}

    def remove_codes(self, element_key: str, codes: list[str], *,
                     actor: str | None = None, actor_role: str | None = None) -> dict[str, Any]:
        """Delete editable (``empty`` / ``draft``) code rows outright (5b.3.1).

        Only rows in :data:`EDITABLE_STATUSES` among ``codes`` are removed; ``in_review`` /
        ``approved`` rows are frozen and skipped. Every deletion persists a ``removed`` audit
        transition before the row is dropped (full auditability). Returns ``{removed, codes}``.
        """
        wanted = {str(c) for c in codes}
        removed: list[str] = []
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key)
                .with_for_update()
            ).scalars().all()
            for row in rows:
                if row.code not in wanted or row.status not in EDITABLE_STATUSES:
                    continue
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE,
                    subject_ref=f"{element_key}|{row.code}",
                    from_status=row.status, to_status="removed",
                    actor=actor, actor_role=actor_role, reason="remove",
                ))
                removed.append(row.code)
                s.delete(row)
        self._summary_cache = None
        return {"removed": len(removed), "codes": removed}

    def approve_codes(self, element_key: str, codes: list[str], *,
                      actor: str | None = None, actor_role: str | None = None) -> dict[str, Any]:
        """Steward approves submitted codes: ``in_review`` → ``approved`` (5b.3.2).

        Only rows currently ``in_review`` among ``codes`` are affected. Records the transition
        and stamps ``approved_at`` / ``approved_by``. Returns ``{approved, codes}``.

        Also opens a new dated window (historize-reference-codes): ``valid_from`` becomes this
        approval's real timestamp for every approval after the code's first-ever one (detected
        via a prior ``reference_code_history`` row existing), regardless of whether the
        re-approved content matches what was there before a revoke — a gap is itself meaningful,
        not a no-op. The very first-ever approval uses the business-effective sentinel instead.
        """
        wanted = {str(c) for c in codes}
        approved: list[str] = []
        with session_scope(self._dsn) as s:
            rows = s.execute(
                select(ReferenceCode)
                .where(ReferenceCode.element_key == element_key,
                       ReferenceCode.status == "in_review")
                .with_for_update()
            ).scalars().all()
            for row in rows:
                if row.code not in wanted:
                    continue
                has_prior_history = s.execute(
                    select(func.count()).select_from(ReferenceCodeHistory)
                    .where(ReferenceCodeHistory.reference_code_id == row.id)
                ).scalar_one() > 0
                row.status = "approved"
                row.approved_at = func.now()
                row.approved_by = actor
                row.updated_at = func.now()
                row.valid_from = func.now() if has_prior_history else _VALID_FROM_SENTINEL
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE,
                    subject_ref=f"{element_key}|{row.code}",
                    from_status="in_review", to_status="approved",
                    actor=actor, actor_role=actor_role, reason="approve",
                ))
                approved.append(row.code)
        self._summary_cache = None
        return {"approved": len(approved), "codes": approved}

    @staticmethod
    def _close_current_into_history(session, row: ReferenceCode, *, valid_to) -> None:
        """Snapshot *row*'s CURRENT fields into ``reference_code_history``, closing that version
        with a real ``valid_to``. Must be called BEFORE the caller mutates *row* — this is what
        makes the retired version reproducible later via :meth:`as_of`.
        """
        session.add(ReferenceCodeHistory(
            reference_code_id=row.id,
            element_key=row.element_key,
            code=row.code,
            value=row.value,
            meaning=row.meaning,
            origin=row.origin,
            status=row.status,
            submitted_at=row.submitted_at,
            submitted_by=row.submitted_by,
            approved_at=row.approved_at,
            approved_by=row.approved_by,
            valid_from=row.valid_from,
            valid_to=valid_to,
        ))

    # ── add-profile-reset: soft-reset — never opens its own transaction ─────────

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> int:
        """Reset every code row for every coded column of this table back to fully blank
        (``'empty'``, no value/meaning) — a full reset, not merely the ``revoke`` unwind (which
        only returns an ``approved`` code to editable ``'draft'``). Closes the outgoing version
        into ``reference_code_history`` first for any row that was ``approved`` (reusing
        ``revoke_codes()``'s own window-closing step, D9) — nothing is hard-deleted.

        Takes a caller-managed *session* (D3) — never opens its own transaction. Returns the
        number of code rows actually cleared (already-empty rows are skipped, keeping repeated
        calls idempotent).
        """
        prefix = f"{source}|{schema or ''}|{table}|"
        now = datetime.now(timezone.utc)
        rows = session.execute(
            select(ReferenceCode).where(ReferenceCode.element_key.like(f"{prefix}%")).with_for_update()
        ).scalars().all()

        cleared = 0
        for row in rows:
            if row.status == "empty" and row.value is None and row.meaning is None:
                continue
            from_status = row.status
            if row.status == "approved":
                self._close_current_into_history(session, row, valid_to=now)
            row.status = "empty"
            row.value = None
            row.meaning = None
            row.submitted_at = None
            row.submitted_by = None
            row.approved_at = None
            row.approved_by = None
            row.updated_at = now
            session.add(LifecycleTransition(
                subject_type=SUBJECT_TYPE, subject_ref=f"{row.element_key}|{row.code}",
                from_status=from_status, to_status="profile_reset",
                actor=None, actor_role=None, reason="profile_reset",
            ))
            cleared += 1
        if cleared:
            self._summary_cache = None
        return cleared

    def clear_for_source(self, session, source: str) -> int:
        """Reset every reference-code row for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        keys = session.execute(
            select(ReferenceCode.element_key).where(ReferenceCode.element_key.like(f"{prefix}%"))
        ).scalars().all()
        tables = {
            (parts[1] or None, parts[2])
            for parts in (k.split("|", 3) for k in set(keys))
            if len(parts) == 4
        }
        return sum(self.clear_for_table(session, source, schema, table) for schema, table in tables)

    def as_of(self, element_key: str, code: str, as_of_date) -> dict[str, Any] | None:
        """Return the officially approved ``{value, meaning}`` for *code* as of *as_of_date*.

        Checks the current row first (cheap, the common case): if it is PRESENTLY approved and
        its window covers *as_of_date*, that's the answer. The presently-approved check matters
        — a revoked/draft row's live fields can be mid-edit and must never be mistaken for a
        stable historical answer. Otherwise falls back to ``reference_code_history`` for an
        older, closed window. Returns ``None`` ("not found") for any date inside a revoked gap —
        no approved value existed then, and this lookup does not separately explain why (that's
        answerable via ``lifecycle_transition`` if ever needed, out of scope here).
        """
        with session_scope(self._dsn) as s:
            row = s.execute(
                select(ReferenceCode).where(
                    ReferenceCode.element_key == element_key, ReferenceCode.code == code,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if row.status == "approved" and as_of_date >= row.valid_from:
                return {"value": row.value, "meaning": row.meaning,
                        "valid_from": row.valid_from, "valid_to": None}
            hist = s.execute(
                select(ReferenceCodeHistory).where(
                    ReferenceCodeHistory.element_key == element_key,
                    ReferenceCodeHistory.code == code,
                    ReferenceCodeHistory.valid_from <= as_of_date,
                    ReferenceCodeHistory.valid_to > as_of_date,
                )
            ).scalar_one_or_none()
            if hist is None:
                return None
            return {"value": hist.value, "meaning": hist.meaning,
                    "valid_from": hist.valid_from, "valid_to": hist.valid_to}


    # ── review-queue reads (5b.3.2) ──────────────────────────────────────────
    def tombstones(self, element_key: str) -> dict[str, dict[str, Any]]:
        """Codes whose LATEST lifecycle action was a pull-back (withdrawn/revoked).

        A tombstone is a queue-rendering trace, derived from the newest transition per code —
        it clears automatically once the code is resubmitted (a later ``in_review`` transition).
        Returns ``{code: {"action": <withdrawn|revoked>, "at": <iso>}}``.
        """
        with session_scope(self._dsn) as s:
            latest = self._latest_transitions(s, element_key)
        return {
            code: {"action": tr.to_status,
                   "at": tr.occurred_at.isoformat() if tr.occurred_at else None}
            for code, tr in latest.items()
            if tr.to_status in (WITHDRAWN, REVOKED)
        }

    def pending_codesets(self, source: str | None = None) -> list[dict[str, Any]]:
        """Columns with reviewable reference codes — ≥1 ``in_review`` code OR ≥1 active tombstone.

        Feeds the steward Review Workspace queue (one entry per column). ``source`` limits to a
        single source. Returns per-column dicts with in-review + tombstone counts.
        """
        with session_scope(self._dsn) as s:
            code_rows = s.execute(select(ReferenceCode)).scalars().all()
            tr_rows = s.execute(
                select(LifecycleTransition)
                .where(LifecycleTransition.subject_type == SUBJECT_TYPE)
                .order_by(LifecycleTransition.occurred_at, LifecycleTransition.id)
            ).scalars().all()

        by_key: dict[str, list[ReferenceCode]] = {}
        for r in code_rows:
            by_key.setdefault(r.element_key, []).append(r)
        latest_action: dict[str, str] = {}
        for tr in tr_rows:
            latest_action[tr.subject_ref] = tr.to_status  # ascending order → last wins

        out: list[dict[str, Any]] = []
        for key, rows in by_key.items():
            if source and not key.startswith(f"{source}|"):
                continue
            in_review = [r for r in rows if r.status == "in_review"]
            tombstones = sum(
                1 for r in rows
                if latest_action.get(f"{key}|{r.code}") in (WITHDRAWN, REVOKED)
            )
            if not in_review and not tombstones:
                continue
            parts = key.split("|")
            submitted = [r.submitted_at for r in in_review if r.submitted_at]
            out.append({
                "key": key,
                "source": parts[0] if len(parts) > 0 else "",
                "schema": parts[1] if len(parts) > 1 else "",
                "table": parts[2] if len(parts) > 2 else "",
                "column": parts[3] if len(parts) > 3 else "",
                "in_review_count": len(in_review),
                "tombstone_count": tombstones,
                "submitted_at": min(submitted).isoformat() if submitted else None,
            })
        return out

    def _latest_transitions(self, session, element_key: str) -> dict[str, LifecycleTransition]:
        """Newest lifecycle_transition per code for one column (code → transition)."""
        rows = session.execute(
            select(LifecycleTransition)
            .where(LifecycleTransition.subject_type == SUBJECT_TYPE,
                   LifecycleTransition.subject_ref.like(f"{element_key}|%"))
            .order_by(LifecycleTransition.occurred_at, LifecycleTransition.id)
        ).scalars().all()
        latest: dict[str, LifecycleTransition] = {}
        for tr in rows:
            code = tr.subject_ref.rsplit("|", 1)[1]
            latest[code] = tr  # ascending order → last write wins
        return latest

