"""Audit feature model — moved from core/glossary_db/models.py (S0 models split)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from core.shared.models.base import Base


class AuditEvent(Base):
    """Append-only audit log (Audit → Postgres, 2026-08-03).

    One row per business/AI event. Mirrors the DuckDB store (core/audit/store.py);
    db/migrations/versions/0007_add_audit_events.py is the source-of-truth DDL.
    """
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_subject", "subject_type", "subject_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False)
    event_class: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(Text)
    actor_role: Mapped[str | None] = mapped_column(Text)
    legal_entity: Mapped[str | None] = mapped_column(Text)
    subject_type: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(Text)
