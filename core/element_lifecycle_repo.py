"""Postgres-backed lifecycle store for Data Element Interpretation Sets (Phase 5a).

Mirrors the *review / lifecycle slice* of ``core.element_state`` (the single lifecycle
status + the submission overlay) onto the generic ``review_subject`` / ``review_task`` /
``lifecycle_transition`` tables built in Phase 1, using the canonical Phase-5 vocabulary
(``core.lifecycle``).

Explicitly NOT owned here (they stay in the YAML store until a later slice): descriptions,
business names, data stories, assessment scope, reference bindings, metadata.

Flag-gated behind ``element_backend()`` — default ``'yaml'`` keeps the running app on the
file store, untouched, until the migration + parity diff are green and the flag is flipped.

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select

from core import lifecycle as lc
from core.glossary_db.db import session_scope
from core.shared.models import LifecycleTransition, ReviewSubject, ReviewTask

_ROOT = Path(__file__).resolve().parents[1]

SUBJECT_TYPE = "element_interpretation"
TASK_TYPE = "interpretation_review"
_DEFAULT_STATUS = "empty"

#: Cache of the project.yaml element_backend value (does not change without a restart).
#: The ADIRRA_ELEMENT_BACKEND env override is checked first and is always live.
_PROJECT_BACKEND_CACHE: str | None = None


def element_backend() -> str:
    """Return the configured element-lifecycle backend: 'yaml' (default) or 'postgres'.

    ``ADIRRA_ELEMENT_BACKEND`` env var wins (live, per-call — used by tests). Otherwise the
    ``project.yaml`` ``database.element_backend`` value is read once and cached (it is on
    the DQ hot path via ``element_state.get`` — re-reading the file per column would be
    wasteful).
    """
    env = os.environ.get("ADIRRA_ELEMENT_BACKEND")
    if env:
        return env.strip().lower()
    global _PROJECT_BACKEND_CACHE
    if _PROJECT_BACKEND_CACHE is None:
        try:
            with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
                db = (yaml.safe_load(fh) or {}).get("database", {}) or {}
            _PROJECT_BACKEND_CACHE = str(db.get("element_backend", "yaml")).strip().lower()
        except Exception:
            _PROJECT_BACKEND_CACHE = "yaml"
    return _PROJECT_BACKEND_CACHE


def make_key(source: str, schema: str | None, table: str, column: str) -> str:
    """The element subject_ref — identical shape to ``ElementStateStore.key``."""
    return f"{source}|{schema or ''}|{table}|{column}"


class ElementLifecycleRepo:
    """Data-access for the element-interpretation lifecycle on Postgres.

    Every write is one transaction: it row-locks (or creates) the ``review_subject``,
    updates ``current_state``, appends a ``lifecycle_transition`` (audit/History), and —
    for submit/decision actions — opens or closes a ``review_task``.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        # Short-TTL batched cache of the whole element-interpretation status map.
        # The DQ hot path + the source/dataset overviews call get_status() once PER
        # COLUMN in tight loops; without this each call was a separate Postgres
        # round-trip (hundreds per page). One all_states() query per TTL window
        # replaces them. Invalidated on every write so reads stay correct.
        self._states_cache: dict[str, str] | None = None
        self._states_ts: float = 0.0
        self._states_ttl: float = 2.0

    # ── internal: subject upsert + transition ────────────────────────────────
    def _apply(self, session, key: str, *, action: str, resting: str,
               actor: str | None, actor_role: str | None, reason: str | None):
        """Set current_state=``resting`` and append a transition to_status=``action``.

        ``action`` is the audit label (may be a TRANSITION_ONLY status like 'withdrawn');
        ``resting`` is the status the subject actually rests in (always in RESTING_STATUSES).
        """
        subj = session.execute(
            select(ReviewSubject)
            .where(ReviewSubject.subject_type == SUBJECT_TYPE,
                   ReviewSubject.subject_ref == key)
            .with_for_update()
        ).scalar_one_or_none()
        from_status = subj.current_state if subj else None
        if subj is None:
            # Per-column subject_ref makes a concurrent first-insert on the SAME key
            # unlikely, but guard the race anyway (INSERT .. ON CONFLICT DO NOTHING).
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            session.execute(
                pg_insert(ReviewSubject.__table__)
                .values(subject_type=SUBJECT_TYPE, subject_ref=key, current_state=resting)
                .on_conflict_do_nothing(index_elements=["subject_type", "subject_ref"])
            )
            subj = session.execute(
                select(ReviewSubject)
                .where(ReviewSubject.subject_type == SUBJECT_TYPE,
                       ReviewSubject.subject_ref == key)
                .with_for_update()
            ).scalar_one()
            # If another writer created it first, honour our intended resting state.
            subj.current_state = resting
        else:
            subj.current_state = resting
            subj.updated_at = func.now()
        session.add(LifecycleTransition(
            subject_type=SUBJECT_TYPE, subject_ref=key,
            from_status=from_status, to_status=action,
            actor=actor, actor_role=actor_role, reason=reason,
        ))
        self._states_cache = None  # invalidate the read cache on any write
        return subj

    def _open_task(self, session, subject_id: int) -> None:
        session.add(ReviewTask(
            review_subject_id=subject_id, task_type=TASK_TYPE, state="open",
        ))

    def _close_open_tasks(self, session, subject_id: int, *, state: str,
                          decided_by: str | None, decided_by_role: str | None,
                          decision: str | None, reason: str | None) -> None:
        tasks = session.execute(
            select(ReviewTask)
            .where(ReviewTask.review_subject_id == subject_id,
                   ReviewTask.state.in_(("open", "in_progress")))
            .with_for_update()
        ).scalars().all()
        for t in tasks:
            t.state = state
            t.decided_by = decided_by
            t.decided_by_role = decided_by_role
            t.decision = decision
            t.reason = reason
            t.decided_at = func.now()

    # ── reads ────────────────────────────────────────────────────────────────
    def get_status(self, key: str) -> str:
        now = time.monotonic()
        if self._states_cache is None or (now - self._states_ts) > self._states_ttl:
            self._states_cache = self.all_states()
            self._states_ts = now
        return self._states_cache.get(key, _DEFAULT_STATUS)

    def all_states(self, source: str | None = None) -> dict[str, str]:
        with session_scope(self._dsn) as s:
            q = select(ReviewSubject.subject_ref, ReviewSubject.current_state).where(
                ReviewSubject.subject_type == SUBJECT_TYPE)
            if source:
                q = q.where(ReviewSubject.subject_ref.like(f"{source}|%"))
            rows = s.execute(q).all()
        return {ref: state for ref, state in rows}

    def counts_by_state(self, source: str | None = None) -> dict[str, int]:
        with session_scope(self._dsn) as s:
            q = select(ReviewSubject.current_state, func.count()).where(
                ReviewSubject.subject_type == SUBJECT_TYPE)
            if source:
                q = q.where(ReviewSubject.subject_ref.like(f"{source}|%"))
            rows = s.execute(q.group_by(ReviewSubject.current_state)).all()
        return {state: n for state, n in rows}

    def get_review(self, key: str) -> dict[str, Any]:
        """Compatibility overlay mirroring ``ElementStateStore.get_submission_status``."""
        with session_scope(self._dsn) as s:
            subj = s.execute(
                select(ReviewSubject).where(
                    ReviewSubject.subject_type == SUBJECT_TYPE,
                    ReviewSubject.subject_ref == key)
            ).scalar_one_or_none()
            submitted_at = submitted_by = None
            decided_at = decided_by = decision = reject_reason = None
            if subj is not None:
                sub_tr = s.execute(
                    select(LifecycleTransition)
                    .where(LifecycleTransition.subject_type == SUBJECT_TYPE,
                           LifecycleTransition.subject_ref == key,
                           LifecycleTransition.to_status == "in_review")
                    .order_by(LifecycleTransition.occurred_at.desc())
                ).scalars().first()
                if sub_tr is not None:
                    submitted_at = sub_tr.occurred_at.isoformat() if sub_tr.occurred_at else None
                    submitted_by = sub_tr.actor
                task = s.execute(
                    select(ReviewTask)
                    .where(ReviewTask.review_subject_id == subj.id,
                           ReviewTask.decided_at.is_not(None))
                    .order_by(ReviewTask.decided_at.desc())
                ).scalars().first()
                if task is not None:
                    decided_at = task.decided_at.isoformat() if task.decided_at else None
                    decided_by = task.decided_by
                    decision = task.decision
                    reject_reason = task.reason
        return {
            "submitted_at": submitted_at, "submitted_by": submitted_by,
            "decided_at": decided_at, "decided_by": decided_by,
            "decision": decision, "reject_reason": reject_reason,
        }

    def last_transition(self, key: str) -> dict[str, Any] | None:
        """Newest lifecycle_transition for this interpretation (action label + when)."""
        with session_scope(self._dsn) as s:
            tr = s.execute(
                select(LifecycleTransition)
                .where(LifecycleTransition.subject_type == SUBJECT_TYPE,
                       LifecycleTransition.subject_ref == key)
                .order_by(LifecycleTransition.occurred_at.desc(), LifecycleTransition.id.desc())
            ).scalars().first()
            if tr is None:
                return None
            return {
                "action": tr.to_status,
                "at": tr.occurred_at.isoformat() if tr.occurred_at else None,
                "actor_role": tr.actor_role,
            }

    def pending_review(self, source: str | None = None) -> list[dict[str, Any]]:
        """Subjects awaiting a steward decision (current_state == 'in_review')."""
        with session_scope(self._dsn) as s:
            q = select(ReviewSubject).where(
                ReviewSubject.subject_type == SUBJECT_TYPE,
                ReviewSubject.current_state == "in_review")
            if source:
                q = q.where(ReviewSubject.subject_ref.like(f"{source}|%"))
            subs = s.execute(q).scalars().all()
            out: list[dict[str, Any]] = []
            for subj in subs:
                parts = subj.subject_ref.split("|", 3)
                out.append({
                    "key": subj.subject_ref,
                    "source": parts[0] if len(parts) > 0 else "",
                    "schema": parts[1] if len(parts) > 1 else "",
                    "table": parts[2] if len(parts) > 2 else "",
                    "column": parts[3] if len(parts) > 3 else "",
                    "state": subj.current_state,
                })
        return out

    # ── writes (each = one transaction) ──────────────────────────────────────
    def set_status(self, key: str, status: str, *, actor: str | None = None,
                   actor_role: str | None = None, reason: str | None = None) -> None:
        """Generic transition to a RESTING status (no task side effects)."""
        if status not in lc.RESTING_STATUSES:
            raise ValueError(f"Not a resting status: {status!r}")
        with session_scope(self._dsn) as s:
            self._apply(s, key, action=status, resting=status,
                        actor=actor, actor_role=actor_role, reason=reason)

    def save(self, key: str, *, has_content: bool = True, actor: str | None = None,
             actor_role: str | None = None) -> None:
        """Holistic Save → rests in 'draft' (content present) or 'empty' (title-only, D4)."""
        from core.lifecycle_vocab import derive_saved_state
        self.set_status(key, derive_saved_state(has_content), actor=actor, actor_role=actor_role)

    def submit(self, key: str, *, actor: str | None = None, actor_role: str | None = None) -> None:
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="in_review", resting="in_review",
                               actor=actor, actor_role=actor_role, reason=None)
            s.flush()
            self._open_task(s, subj.id)

    def withdraw(self, key: str, *, actor: str | None = None, actor_role: str | None = None) -> None:
        """Analyst pulls a submission back → rests in 'draft' (audit keeps 'withdrawn')."""
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="withdrawn", resting="draft",
                               actor=actor, actor_role=actor_role, reason=None)
            s.flush()
            self._close_open_tasks(s, subj.id, state="cancelled", decided_by=actor,
                                   decided_by_role=actor_role, decision="withdrawn", reason=None)

    def approve(self, key: str, *, decided_by: str | None = None,
                decided_by_role: str | None = None) -> None:
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="approved", resting="approved",
                               actor=decided_by, actor_role=decided_by_role, reason=None)
            s.flush()
            self._close_open_tasks(s, subj.id, state="approved", decided_by=decided_by,
                                   decided_by_role=decided_by_role, decision="approved", reason=None)

    def reject(self, key: str, *, decided_by: str | None = None,
               decided_by_role: str | None = None, reason: str | None = None) -> None:
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="rejected", resting="rejected",
                               actor=decided_by, actor_role=decided_by_role, reason=reason)
            s.flush()
            self._close_open_tasks(s, subj.id, state="rejected", decided_by=decided_by,
                                   decided_by_role=decided_by_role, decision="rejected", reason=reason)

    def send_back(self, key: str, *, decided_by: str | None = None,
                  decided_by_role: str | None = None, reason: str | None = None) -> None:
        """Steward returns with comments → rests in 'returned' (analyst fixes + resubmits)."""
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="returned", resting="returned",
                               actor=decided_by, actor_role=decided_by_role, reason=reason)
            s.flush()
            self._close_open_tasks(s, subj.id, state="rejected", decided_by=decided_by,
                                   decided_by_role=decided_by_role, decision="returned", reason=reason)

    def revoke(self, key: str, *, actor: str | None = None, actor_role: str | None = None,
               reason: str | None = None) -> None:
        """Revoke a prior approval → rests in 'draft' (editable); audit keeps 'revoked'."""
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="revoked", resting="draft",
                               actor=actor, actor_role=actor_role, reason=reason)
            s.flush()
            self._close_open_tasks(s, subj.id, state="cancelled", decided_by=actor,
                                   decided_by_role=actor_role, decision="revoked", reason=reason)

    # ── add-profile-reset: soft-reset — never opens its own transaction ─────────

    def clear_for_table(self, session, source: str, schema: str | None, table: str, *,
                        actor: str | None = None) -> int:
        """Reset the Interpretation lifecycle status back to its pre-governed default
        (``'empty'``) for every column of this table.

        Reuses ``_apply`` (the same primitive every named transition above wraps) directly with
        the caller's *session* — this records a normal ``lifecycle_transition`` row (append-only,
        exactly like every other status change) and closes any open review task, rather than
        deleting anything.

        Takes a caller-managed *session* (D3) — unlike every public write method above, this
        never opens its own ``session_scope()``, so the reset orchestrator can wrap it in one
        shared transaction with every other store's clear. Returns the number of subjects
        actually reset (already-default subjects are skipped, keeping repeated calls idempotent).
        """
        prefix = f"{source}|{schema or ''}|{table}|"
        subjects = session.execute(
            select(ReviewSubject).where(
                ReviewSubject.subject_type == SUBJECT_TYPE,
                ReviewSubject.subject_ref.like(f"{prefix}%"),
            )
        ).scalars().all()

        cleared = 0
        for subj in subjects:
            if subj.current_state == _DEFAULT_STATUS:
                continue
            self._apply(session, subj.subject_ref, action="profile_reset", resting=_DEFAULT_STATUS,
                       actor=actor, actor_role=None, reason="profile_reset")
            self._close_open_tasks(session, subj.id, state="cancelled", decided_by=actor,
                                   decided_by_role=None, decision="profile_reset", reason=None)
            cleared += 1
        return cleared

    def clear_for_source(self, session, source: str, *, actor: str | None = None) -> int:
        """Reset every Interpretation lifecycle status for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        refs = session.execute(
            select(ReviewSubject.subject_ref).where(
                ReviewSubject.subject_type == SUBJECT_TYPE,
                ReviewSubject.subject_ref.like(f"{prefix}%"),
            )
        ).scalars().all()
        tables = {
            (parts[1] or None, parts[2])
            for parts in (ref.split("|", 3) for ref in refs)
            if len(parts) == 4
        }
        return sum(
            self.clear_for_table(session, source, schema, table, actor=actor)
            for schema, table in tables
        )
