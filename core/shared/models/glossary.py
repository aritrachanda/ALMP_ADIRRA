"""Glossary feature models — moved from core/glossary_db/models.py (S0 models split).

Mirrors db/migrations/versions/0001_initial_glossary_schema.py (+ 0002 last_reviewed,
0003 triage/group_meta, 0004 is_cde/ai_provenance). The hand-written migrations remain the
source of truth for generated columns, partial indexes and CHECK constraints; this metadata
is wired into Alembic env.py so future autogenerate has a reference (advisory only).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.shared.models.base import Base

_TSV_EXPR = (
    "to_tsvector('english'::regconfig, "
    "coalesce(title,'') || ' ' || coalesce(business_description,'') || ' ' || "
    "coalesce(detailed_description,'') || ' ' || glossary_text_join(synonyms,' ') || ' ' || "
    "glossary_text_join(tags,' '))"
)


class Glossary(Base):
    __tablename__ = "glossary"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class Term(Base):
    __tablename__ = "term"
    __table_args__ = (
        UniqueConstraint("glossary_id", "slug"),
        CheckConstraint("status IN ('empty','draft','in_review','approved','deprecated','rejected')",
                        name="term_status_check"),
        Index("ix_term_status", "status"),
        Index("ix_term_domain_category", "domain", "category"),
        Index("ix_term_steward", "steward"),
        Index("ix_term_parent", "parent_term_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    glossary_id: Mapped[int] = mapped_column(ForeignKey("glossary.id", ondelete="CASCADE"), nullable=False)
    parent_term_id: Mapped[int | None] = mapped_column(ForeignKey("term.id", ondelete="SET NULL"))
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    steward: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    next_review_due: Mapped[date | None] = mapped_column()
    last_reviewed: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_cde: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    versions: Mapped[list["TermVersion"]] = relationship(
        back_populates="term", cascade="all, delete-orphan")
    linkages: Mapped[list["Linkage"]] = relationship(
        back_populates="term", cascade="all, delete-orphan")


class TermVersion(Base):
    __tablename__ = "term_version"
    __table_args__ = (
        UniqueConstraint("term_id", "version_no"),
        CheckConstraint("status IN ('draft','approved','superseded')", name="term_version_status_check"),
        Index("uq_term_version_current_approved", "term_id",
              unique=True, postgresql_where=text("is_current_approved")),
        Index("ix_term_version_search", "search_tsv", postgresql_using="gin"),
        Index("ix_term_version_title_trgm", "title",
              postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_term_version_synonyms", "synonyms", postgresql_using="gin"),
        Index("ix_term_version_attributes", "attributes", postgresql_using="gin"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    business_description: Mapped[str | None] = mapped_column(Text)
    detailed_description: Mapped[str | None] = mapped_column(Text)
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    attributes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ai_generated_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    ai_provenance: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    is_current_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    authored_by: Mapped[str | None] = mapped_column(Text)
    authored_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR, Computed(_TSV_EXPR, persisted=True))

    term: Mapped["Term"] = relationship(back_populates="versions")


class TermRelation(Base):
    __tablename__ = "term_relation"
    __table_args__ = (
        CheckConstraint("relation_type IN ('broader','narrower','related','synonym_of')",
                        name="term_relation_type_check"),
        CheckConstraint("to_term_id IS NOT NULL OR to_label IS NOT NULL",
                        name="term_relation_target_check"),
        UniqueConstraint("from_term_id", "relation_type", "to_term_id", "to_label"),
        Index("ix_term_relation_from", "from_term_id"),
        Index("ix_term_relation_to", "to_term_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_term_id: Mapped[int] = mapped_column(ForeignKey("term.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    to_term_id: Mapped[int | None] = mapped_column(ForeignKey("term.id", ondelete="CASCADE"))
    to_label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class Linkage(Base):
    __tablename__ = "linkage"
    __table_args__ = (
        CheckConstraint("kind IN ('source','target')", name="linkage_kind_check"),
        CheckConstraint("granularity IN ('dataset','table','column')", name="linkage_granularity_check"),
        CheckConstraint("status IN ('active','needs_revalidation','stale')", name="linkage_status_check"),
        CheckConstraint("origin IN ('human','ai','migrated')", name="linkage_origin_check"),
        UniqueConstraint("term_id", "raw_ref"),
        Index("ix_linkage_target", "kind", "dataset", "schema_name", "table_name", "column_name"),
        Index("ix_linkage_term", "term_id"),
        Index("ix_linkage_needs_reval", "status", postgresql_where=text("status = 'needs_revalidation'")),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    granularity: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[str] = mapped_column(Text, nullable=False)
    schema_name: Mapped[str | None] = mapped_column(Text)
    table_name: Mapped[str | None] = mapped_column(Text)
    column_name: Mapped[str | None] = mapped_column(Text)
    raw_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="migrated")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    rationale: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    term: Mapped["Term"] = relationship(back_populates="linkages")


class LinkageTriage(Base):
    __tablename__ = "linkage_triage"
    __table_args__ = (
        Index("ix_triage_reason", "reason"),
        Index("ix_triage_term", "term_slug"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    term_slug: Mapped[str] = mapped_column(Text, nullable=False)
    raw_ref: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str | None] = mapped_column(Text)
    dataset: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class GlossaryGroupMeta(Base):
    __tablename__ = "glossary_group_meta"
    __table_args__ = (
        CheckConstraint("group_type IN ('domain','category')", name="glossary_group_meta_type_check"),
        UniqueConstraint("glossary_id", "group_type", "name"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    glossary_id: Mapped[int] = mapped_column(ForeignKey("glossary.id", ondelete="CASCADE"), nullable=False)
    group_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
