"""Postgres-backed review lifecycle for a column's reference-set BINDING (govern-pg-d follow-up).

The binding itself (which set a column points to) lives in ``element_reference_binding``
(``core.reference_set_repo``). This is a SEPARATE concern: whether that binding decision has
been submitted for steward review and approved — tracked on the same generic
``review_subject``/``review_task``/``lifecycle_transition`` tables every other governance
lifecycle already uses (``subject_type='reference_binding'``), reusing the canonical Phase-5
status vocabulary. No new table — user decision 2026-08-16 (option b): reuse the existing
generic review mechanism rather than adding status columns to the binding table itself.

Deliberately mirrors ``core.element_lifecycle_repo.ElementLifecycleRepo``'s shape (a second,
independent instance of the same proven pattern — same precedent as ``ReferenceCodeRepo`` being
its own class rather than a generalisation of the interpretation lifecycle), but kept as its own
small class since the binding's lifecycle is simpler: submit / approve / withdraw / revoke only
— no separate steward "reject", mirroring ``reference_code``'s own shape exactly (which also has
no reject, only revoke-an-approved-row / withdraw-an-in_review-row as the reversal paths).

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, func, select

from core.glossary_db.db import session_scope
from core.shared.models import LifecycleTransition, ReviewSubject, ReviewTask

SUBJECT_TYPE = "reference_binding"
TASK_TYPE = "reference_binding_review"
_DEFAULT_STATUS = "draft"


class ReferenceBindingReviewRepo:
    """Data-access for a column's reference-set binding review lifecycle on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        # Short-TTL batched cache — same reasoning as ElementLifecycleRepo's own cache
        # (this is read on the DQ hot path, one call per bound column).
        self._states_cache: dict[str, str] | None = None
        self._states_ts: float = 0.0
        self._states_ttl: float = 2.0

    def _invalidate(self) -> None:
        self._states_cache = None

    # ── internal: subject upsert + transition (mirrors ElementLifecycleRepo._apply) ──
    def _apply(self, session, key: str, *, action: str, resting: str,
               actor: str | None, actor_role: str | None, reason: str | None):
        subj = session.execute(
            select(ReviewSubject)
            .where(ReviewSubject.subject_type == SUBJECT_TYPE,
                   ReviewSubject.subject_ref == key)
            .with_for_update()
        ).scalar_one_or_none()
        from_status = subj.current_state if subj else None
        if subj is None:
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
            subj.current_state = resting
        else:
            subj.current_state = resting
            subj.updated_at = func.now()
        session.add(LifecycleTransition(
            subject_type=SUBJECT_TYPE, subject_ref=key,
            from_status=from_status, to_status=action,
            actor=actor, actor_role=actor_role, reason=reason,
        ))
        self._invalidate()
        return subj

    def _open_task(self, session, subject_id: int) -> None:
        session.add(ReviewTask(review_subject_id=subject_id, task_type=TASK_TYPE, state="open"))

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
        """Current binding-review status, defaulting to 'draft' (bound, never submitted)."""
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

    def get_review(self, key: str) -> dict[str, Any]:
        """submitted/decided who+when, mirroring ElementLifecycleRepo.get_review's shape."""
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

    def pending_review(self, source: str | None = None) -> list[dict[str, Any]]:
        """Bindings awaiting a steward decision (current_state == 'in_review')."""
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
    def reset_to_draft(self, key: str, *, actor: str | None = None,
                       actor_role: str | None = None) -> None:
        """Called on a fresh Bind (and on Unbind) — rests the binding's own review state back
        at 'draft', clearing any prior submitted/approved history's CURRENT state (the history
        rows themselves stay in lifecycle_transition, untouched, for the audit trail).
        """
        with session_scope(self._dsn) as s:
            self._apply(s, key, action="draft", resting="draft",
                       actor=actor, actor_role=actor_role, reason=None)

    def submit(self, key: str, *, actor: str | None = None, actor_role: str | None = None) -> None:
        with session_scope(self._dsn) as s:
            subj = self._apply(s, key, action="in_review", resting="in_review",
                               actor=actor, actor_role=actor_role, reason=None)
            s.flush()
            self._open_task(s, subj.id)

    def withdraw(self, key: str, *, actor: str | None = None, actor_role: str | None = None) -> None:
        """Analyst pulls a submitted binding back → rests in 'draft'."""
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

    def revoke(self, key: str, *, actor: str | None = None, actor_role: str | None = None) -> None:
        """Steward pulls an approved binding back → rests in 'draft' (mirrors reference_code's
        own revoke, an analyst/steward pull-back rather than a rejection)."""
        with session_scope(self._dsn) as s:
            self._apply(s, key, action="revoked", resting="draft",
                       actor=actor, actor_role=actor_role, reason=None)

    # ── add-profile-reset: hard delete, unlike ElementLifecycleRepo's soft-reset ────

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> int:
        """Delete every column's reference-set BINDING review subject for this table.

        Hard delete, not soft-reset (unlike ``ElementLifecycleRepo.clear_for_table``): once the
        binding itself is gone (``ReferenceSetRepo.clear_for_table``), a review subject about a
        binding that no longer exists is meaningless, not merely reset-to-draft. Deleting
        ``ReviewSubject`` cascades its ``ReviewTask`` rows (``ON DELETE CASCADE``);
        ``LifecycleTransition`` has no FK to ``ReviewSubject``, so it is deleted explicitly too.

        Takes a caller-managed *session* (D3) — never opens its own transaction. Returns the
        number of review subjects removed.
        """
        prefix = f"{source}|{schema or ''}|{table}|"
        subjects = session.execute(
            select(ReviewSubject).where(
                ReviewSubject.subject_type == SUBJECT_TYPE,
                ReviewSubject.subject_ref.like(f"{prefix}%"),
            )
        ).scalars().all()
        if not subjects:
            return 0
        refs = [subj.subject_ref for subj in subjects]
        session.execute(
            delete(LifecycleTransition).where(
                LifecycleTransition.subject_type == SUBJECT_TYPE,
                LifecycleTransition.subject_ref.in_(refs),
            )
        )
        for subj in subjects:
            session.delete(subj)
        self._invalidate()
        return len(subjects)

    def clear_for_source(self, session, source: str) -> int:
        """Delete every reference-set-binding review subject for *source* — see
        :meth:`clear_for_table`."""
        prefix = f"{source}|"
        subjects = session.execute(
            select(ReviewSubject).where(
                ReviewSubject.subject_type == SUBJECT_TYPE,
                ReviewSubject.subject_ref.like(f"{prefix}%"),
            )
        ).scalars().all()
        if not subjects:
            return 0
        refs = [subj.subject_ref for subj in subjects]
        session.execute(
            delete(LifecycleTransition).where(
                LifecycleTransition.subject_type == SUBJECT_TYPE,
                LifecycleTransition.subject_ref.in_(refs),
            )
        )
        for subj in subjects:
            session.delete(subj)
        self._invalidate()
        return len(subjects)
