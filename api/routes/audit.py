"""Audit log read-only API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_audit_store
from core.audit import AuditStore

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
async def list_events(
    event_class: str | None = None,
    event_type: str | None = None,
    event_prefix: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    limit: int = 50,
    offset: int = 0,
    store: AuditStore = Depends(get_audit_store),
):
    return store.list_events(
        event_class=event_class,
        event_type=event_type,
        event_prefix=event_prefix,
        subject_type=subject_type,
        subject_id=subject_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=min(limit, 200),
        offset=offset,
    )


@router.get("/events/{event_id}")
async def get_event(event_id: int, store: AuditStore = Depends(get_audit_store)):
    event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Audit event {event_id} not found")
    return event


@router.get("/summary")
async def summary(days: int = 30, store: AuditStore = Depends(get_audit_store)):
    return store.summary(days=days)
