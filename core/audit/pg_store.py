"""Postgres-backed append-only audit store (Audit → Postgres, 2026-08-03).

Interface-compatible with :class:`core.audit.store.AuditStore` (log_business / log_ai_call /
list_events / get_event / summary / close), selected by the ``database.audit_backend`` flag.
Moving the audit log off the process-lifetime DuckDB file lock removes a chief cause of the
single-writer "used by another process" failures when a second ``uvicorn`` starts.

Synchronous psycopg 3 via the shared engine (``core.glossary_db.db``); route handlers run in
FastAPI's threadpool — never call inside an ``async def``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from core.glossary_db.db import session_scope
from core.shared.models import AuditEvent


def _row_to_dict(ev: AuditEvent) -> dict:
    """Shape a row exactly like core.audit.store._row_to_dict (occurred_at as ISO text)."""
    return {
        "id": ev.id,
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
        "event_class": ev.event_class,
        "event_type": ev.event_type,
        "actor_user_id": ev.actor_user_id,
        "actor_role": ev.actor_role,
        "legal_entity": ev.legal_entity,
        "subject_type": ev.subject_type,
        "subject_id": ev.subject_id,
        "payload": ev.payload,
        "request_id": ev.request_id,
    }


class PgAuditStore:
    """Append-only audit log backed by Postgres — interface-compatible with AuditStore."""

    def __init__(self) -> None:
        # Nothing to open/lock at startup — the shared engine's pool manages
        # connections per transaction (this is the whole point of the move).
        pass

    # ── internal ─────────────────────────────────────────────────────────────
    def _append(
        self, event_class: str, event_type: str, subject_type: str | None,
        subject_id: str | None, payload: dict[str, Any], *,
        actor_user_id: str | None = None, actor_role: str | None = None,
        legal_entity: str | None = None, request_id: str | None = None,
    ) -> int:
        with session_scope() as s:
            ev = AuditEvent(
                event_class=event_class, event_type=event_type,
                actor_user_id=actor_user_id, actor_role=actor_role, legal_entity=legal_entity,
                subject_type=subject_type, subject_id=subject_id,
                payload=payload, request_id=request_id,
            )
            s.add(ev)
            s.flush()
            return int(ev.id)

    # ── public write API ──────────────────────────────────────────────────────
    def log_business(
        self, event_type: str, subject_type: str, subject_id: str,
        payload: dict[str, Any], *,
        actor_user_id: str | None = None, actor_role: str | None = None,
        legal_entity: str | None = None, request_id: str | None = None,
    ) -> int:
        return self._append(
            "business", event_type, subject_type, subject_id, payload,
            actor_user_id=actor_user_id, actor_role=actor_role,
            legal_entity=legal_entity, request_id=request_id,
        )

    def log_ai_call(
        self, *, model: str, subject_type: str, subject_id: str,
        prompt_tokens: int = 0, completion_tokens: int = 0, latency_ms: float = 0.0,
        confidence: float | None = None, prompt_id: str | None = None,
        retrieval_chunks: int | None = None, extra: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> int:
        payload: dict[str, Any] = {
            "model": model,
            "prompt_id": prompt_id,
            "retrieval_chunks": retrieval_chunks,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": round(latency_ms, 1),
            "confidence": confidence,
        }
        if extra:
            payload.update(extra)
        return self._append("ai", "ai.call", subject_type, subject_id, payload, request_id=request_id)

    # ── read API ──────────────────────────────────────────────────────────────
    def list_events(
        self, *, event_class: str | None = None, event_type: str | None = None,
        event_prefix: str | None = None, subject_type: str | None = None,
        subject_id: str | None = None, from_ts: str | None = None, to_ts: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        with session_scope() as s:
            stmt = select(AuditEvent)
            if event_class:
                stmt = stmt.where(AuditEvent.event_class == event_class)
            if event_type:
                stmt = stmt.where(AuditEvent.event_type == event_type)
            if event_prefix:
                stmt = stmt.where(AuditEvent.event_type.like(f"{event_prefix}%"))
            if subject_type:
                stmt = stmt.where(AuditEvent.subject_type == subject_type)
            if subject_id:
                stmt = stmt.where(AuditEvent.subject_id.like(f"%{subject_id}%"))
            if from_ts:
                stmt = stmt.where(AuditEvent.occurred_at >= from_ts)
            if to_ts:
                stmt = stmt.where(AuditEvent.occurred_at <= to_ts)
            stmt = (
                stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                .limit(limit).offset(offset)
            )
            return [_row_to_dict(ev) for ev in s.execute(stmt).scalars().all()]

    def get_event(self, event_id: int) -> dict | None:
        with session_scope() as s:
            ev = s.get(AuditEvent, event_id)
            return _row_to_dict(ev) if ev else None

    def summary(self, days: int = 30) -> list[dict]:
        """Counts per (day, event_type) for the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        day = func.to_char(AuditEvent.occurred_at, "YYYY-MM-DD").label("day")
        with session_scope() as s:
            stmt = (
                select(day, AuditEvent.event_type, func.count().label("cnt"))
                .where(AuditEvent.occurred_at >= cutoff)
                .group_by(day, AuditEvent.event_type)
                .order_by(day.desc(), func.count().desc())
            )
            return [
                {"day": r.day, "event_type": r.event_type, "count": int(r.cnt)}
                for r in s.execute(stmt)
            ]

    def close(self) -> None:
        # No persistent connection to close — the engine pool is app-lifetime and shared.
        pass
