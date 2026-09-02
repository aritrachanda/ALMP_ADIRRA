"""Cross-feature review/reference-lifecycle governance models — moved from
core/glossary_db/models.py (S0 models split).

These tables are shared across multiple governance slices (element lifecycle, reference-data
per-code review) rather than owned by a single feature — hence a dedicated ``governance``
module rather than folding them into ``glossary`` or ``catalog``. New governance tables added
by the source-catalog/YAML-to-Postgres migration slices (semantic types, DQ scores, element
content, reference sets, learned patterns, annotations, reference-code history) land here too.

Mirrors db/migrations/versions/0005_add_reference_code.py and the lifecycle-vocab tables from
0001/0006 — those hand-written migrations remain the source of truth for CHECK constraints.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from core.shared.models.base import Base


class LifecycleTransition(Base):
    __tablename__ = "lifecycle_transition"
    __table_args__ = (
        Index("ix_transition_subject", "subject_type", "subject_ref", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_ref: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    actor_role: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ReviewSubject(Base):
    __tablename__ = "review_subject"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_ref"),
        Index("ix_review_subject_state", "subject_type", "current_state"),
        Index("ix_review_subject_assignee", "assigned_to"),
        Index("ix_review_subject_due", "next_review_due"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_ref: Mapped[str] = mapped_column(Text, nullable=False)
    current_state: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    next_review_due: Mapped[date | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ReviewTask(Base):
    __tablename__ = "review_task"
    __table_args__ = (
        CheckConstraint("state IN ('open','in_progress','approved','rejected','cancelled')",
                        name="review_task_state_check"),
        Index("ix_review_task_state", "state"),
        Index("ix_review_task_subject", "review_subject_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_subject_id: Mapped[int] = mapped_column(
        ForeignKey("review_subject.id", ondelete="CASCADE"), nullable=False)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    assigned_to: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_by_role: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ReferenceCode(Base):
    """Per-code reviewable object for a coded column (Phase 5b.2).

    One row per distinct code in a coded column's code list. Carries the steward-entered
    Value / Meaning / Origin and a per-code lifecycle status; approved rows are frozen.
    Mirrors db/migrations/versions/0005_add_reference_code.py (source of truth for the
    CHECK constraints + unique key).
    """
    __tablename__ = "reference_code"
    __table_args__ = (
        CheckConstraint("origin IN ('profiled','declared')", name="reference_code_origin_check"),
        CheckConstraint("status IN ('empty','draft','in_review','approved','returned','rejected')",
                        name="reference_code_status_check"),
        UniqueConstraint("element_key", "code", name="uq_reference_code_element_code"),
        Index("ix_reference_code_element", "element_key"),
        Index("ix_reference_code_status", "element_key", "status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_key: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    meaning: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="profiled")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="empty")
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    submitted_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    valid_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("'1800-01-01 00:00:00+00'::timestamptz"))


class ReferenceCodeHistory(Base):
    """Retired versions of a reference code's value/meaning (historize-reference-codes).

    One row per version that was ever superseded — closed by ``revoke_codes()``, opened by the
    next ``approve_codes()``. ``valid_from``/``valid_to`` are always two real, concrete dates,
    never a placeholder. Mirrors
    db/migrations/versions/0010_add_reference_code_history.py (source of truth for the CHECK
    constraints).
    """
    __tablename__ = "reference_code_history"
    __table_args__ = (
        CheckConstraint("origin IN ('profiled','declared')", name="reference_code_history_origin_check"),
        CheckConstraint(
            "status IN ('empty','draft','in_review','approved','returned','rejected')",
            name="reference_code_history_status_check",
        ),
        CheckConstraint("valid_to > valid_from", name="reference_code_history_window_check"),
        Index("ix_reference_code_history_element_code_window", "element_key", "code", "valid_from"),
        Index("ix_reference_code_history_reference_code_id", "reference_code_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reference_code_id: Mapped[int] = mapped_column(
        ForeignKey("reference_code.id", ondelete="CASCADE"), nullable=False)
    element_key: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    meaning: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    submitted_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class DqScore(Base):
    """Current data-quality score for one column or dataset roll-up (govern-pg-a1-dq-scores-build).

    One row per key (``source|schema|table|column`` for a column, ``source|schema|table`` for a
    dataset roll-up). Real SCD2: ``valid_from`` marks when this row's current score/state took
    effect; every genuine change closes the outgoing version into ``dq_score_history`` first.
    Mirrors db/migrations/versions/0011_add_dq_score.py (source of truth for CHECK constraints).
    """
    __tablename__ = "dq_score"
    __table_args__ = (
        CheckConstraint("key_kind IN ('column','dataset')", name="dq_score_key_kind_check"),
        Index("ix_dq_score_key", "key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_kind: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    dq_score: Mapped[int | None] = mapped_column()
    grade_label: Mapped[str | None] = mapped_column(Text)
    breakdown_version: Mapped[int | None] = mapped_column()
    signal_fingerprint: Mapped[str | None] = mapped_column(Text)
    config_fingerprint: Mapped[str | None] = mapped_column(Text)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class DqScoreHistory(Base):
    """Retired data-quality score versions (govern-pg-a1-dq-scores-build).

    One row per version that was ever superseded for a key — closed the instant a genuine change
    (including a ``scored -> unscored`` transition) supersedes it. ``valid_from``/``valid_to`` are
    always two real, concrete dates, never a placeholder. Mirrors
    db/migrations/versions/0011_add_dq_score.py (source of truth for CHECK constraints).
    """
    __tablename__ = "dq_score_history"
    __table_args__ = (
        CheckConstraint("key_kind IN ('column','dataset')", name="dq_score_history_key_kind_check"),
        CheckConstraint("valid_to > valid_from", name="dq_score_history_window_check"),
        Index("ix_dq_score_history_key_window", "key", "valid_from"),
        Index("ix_dq_score_history_dq_score_id", "dq_score_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dq_score_id: Mapped[int] = mapped_column(ForeignKey("dq_score.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    key_kind: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    dq_score: Mapped[int | None] = mapped_column()
    grade_label: Mapped[str | None] = mapped_column(Text)
    breakdown_version: Mapped[int | None] = mapped_column()
    signal_fingerprint: Mapped[str | None] = mapped_column(Text)
    config_fingerprint: Mapped[str | None] = mapped_column(Text)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class SemanticTypeAssignment(Base):
    """Current semantic-type deduction/decision for one column (govern-pg-b1-semantic-types-build).

    One row per key (``source|schema|table|column``). Near-verbatim mirror of
    ``SemanticTypeStore``'s YAML record shape, plus ``system_deduced_type`` (captures the
    machine's pre-override suggestion the moment a steward first "Replace"s it, fixing a
    data-loss bug). ``latest_proposal`` (the existing sticky-disposition mechanism) carries over
    unchanged. Unlike the YAML record, has NO ``submitted_at``/``submitted_by`` of its own -- a
    semantic type is never submitted on its own, only as part of the whole Interpretation Set, so
    tracking a second "submission" concept here would duplicate the Interpretation Set's own
    submission tracking.

    No persisted ``state`` (retired 2026-08-20, migration 0018 -- untangles tech-debt #13/#36/#45):
    the only two real, reachable outcomes an analyst can produce are the default ``unresolved``
    ``type_id`` and an accepted type (``accepted_at IS NOT NULL``) -- there is no Reject action in
    the UI. "How confident was the guess" is fully carried by ``confidence`` alone (the UI shows a
    High/Medium/Low grade derived from it, never a persisted word). Mirrors
    db/migrations/versions/0012_semantic_type_assignment.py + 0018_semantic_type_retire_state.py
    (source of truth for CHECK constraints).
    """
    __tablename__ = "semantic_type_assignment"
    __table_args__ = (
        CheckConstraint(
            "source IS NULL OR source IN ('rule','ai')",
            name="semantic_type_assignment_source_check",
        ),
        Index("ix_semantic_type_assignment_key", "key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type_id: Mapped[str] = mapped_column(Text, nullable=False)
    domain_role: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(nullable=False, server_default="0")
    source: Mapped[str | None] = mapped_column(Text)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    type_value_conflict: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    type_datatype_difference: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    format: Mapped[str | None] = mapped_column(Text)
    format_source: Mapped[str | None] = mapped_column(Text)
    format_rationale: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(Text)
    pii: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    pii_category: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(nullable=False, server_default="0")
    resolver_version: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(Text)
    accepted_by_role: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fingerprint: Mapped[str | None] = mapped_column(Text)
    system_deduced_type: Mapped[dict | None] = mapped_column(JSONB)
    latest_proposal: Mapped[dict | None] = mapped_column(JSONB)
    # Written by the resolver at runtime, absent from default_record() -- added in 0013 (B2 D1).
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    nearest_candidates: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class SemanticTypeAssignmentHistory(Base):
    """One row per Interpretation Set submission for a column (govern-pg-b1-semantic-types-build).

    Self-contained SCD2 (unlike dq_score/reference_code's separate current+history split): a new
    row opens on every submission (D1), not on every confirm()/reject()/machine re-resolve.
    ``valid_from`` is that submission's own timestamp; ``valid_to`` is NULL while it is still the
    most recent submission for that key, set the moment a later submission supersedes it (a
    partial unique index enforces at most one open row per key).

    Carries the FULL accepted snapshot as real, named columns (same names/shapes as
    ``SemanticTypeAssignment`` -- what a person actually confirmed), plus a separate, smaller
    ``deduced_*`` column group for what the machine's own resolver independently believed at that
    same moment (2026-08-13 user correction -- an earlier draft collapsed most of this into two
    JSONB columns and lost real, queryable history detail). Mirrors
    db/migrations/versions/0012_semantic_type_assignment.py (source of truth for CHECK
    constraints).
    """
    __tablename__ = "semantic_type_assignment_history"
    __table_args__ = (
        CheckConstraint(
            "source IS NULL OR source IN ('rule','ai')",
            name="semantic_type_assignment_history_source_check",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="semantic_type_assignment_history_window_check",
        ),
        Index("ix_semantic_type_assignment_history_key_window", "key", "valid_from"),
        Index("ix_semantic_type_assignment_history_assignment_id", "semantic_type_assignment_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    semantic_type_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("semantic_type_assignment.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)

    # Full accepted snapshot at submission time (same field names/shapes as SemanticTypeAssignment).
    type_id: Mapped[str] = mapped_column(Text, nullable=False)
    domain_role: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(Text)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    type_value_conflict: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    type_datatype_difference: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    format: Mapped[str | None] = mapped_column(Text)
    format_source: Mapped[str | None] = mapped_column(Text)
    format_rationale: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(Text)
    pii: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    pii_category: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(nullable=False, server_default="0")
    resolver_version: Mapped[str | None] = mapped_column(Text)
    accepted_by: Mapped[str | None] = mapped_column(Text)
    accepted_by_role: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fingerprint: Mapped[str | None] = mapped_column(Text)
    # Written by the resolver at runtime, absent from B1's default field list -- added in 0013
    # (B2 D1); table starts empty regardless (D2), this only readies the schema for future rows.
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    nearest_candidates: Mapped[list | None] = mapped_column(JSONB)

    # The machine's own, independent opinion at that same moment (may differ from the accepted
    # snapshot above whenever a steward overrode it).
    deduced_type_id: Mapped[str] = mapped_column(Text, nullable=False)
    deduced_domain_role: Mapped[str | None] = mapped_column(Text)
    deduced_confidence: Mapped[float | None] = mapped_column()
    deduced_tier: Mapped[int | None] = mapped_column()
    deduced_resolver_version: Mapped[str | None] = mapped_column(Text)

    submitted_by: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ElementDefinition(Base):
    """Current human-authored content for one column (govern-pg-c1-element-content-build).

    One row per ``element_key`` (``source|schema|table|column``) holding the definition and
    business name, each with its own AI-authorship flag. Saves land here immediately on Save,
    exactly as the YAML store behaves today; the versioned copy is cut separately at submission
    (see ``ElementDefinitionHistory``). ``criticality`` is deliberately carried but inert -- the
    DQ dataset roll-up can weight critical columns double, but that weighting is switched off in
    config and no record sets the value (user decision 2026-08-15: keep the plumbing, defer the
    feature). Mirrors db/migrations/versions/0014_element_content.py (source of truth for CHECKs).
    """
    __tablename__ = "element_definition"
    __table_args__ = (
        CheckConstraint(
            "criticality IS NULL OR criticality IN ('standard','critical')",
            name="element_definition_criticality_check",
        ),
        Index("ix_element_definition_key", "element_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    definition: Mapped[str | None] = mapped_column(Text)
    definition_is_ai: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    business_name: Mapped[str | None] = mapped_column(Text)
    business_name_is_ai: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    criticality: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ElementDefinitionHistory(Base):
    """Past wording of a column's definition/business name (govern-pg-c1-element-content-build).

    Self-contained SCD2, same shape as ``SemanticTypeAssignmentHistory``: a window opens when the
    column's Interpretation Set is SUBMITTED (not on every intermediate save -- user decision
    2026-08-15, deliberately mirroring the semantic-type rule so both components of one
    Interpretation Set version in lockstep). ``valid_to`` stays NULL while this is the most recent
    submitted wording; a partial unique index allows at most one open window per key.
    """
    __tablename__ = "element_definition_history"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="element_definition_history_window_check",
        ),
        Index("ix_element_definition_history_key_window", "element_key", "valid_from"),
        Index("ix_element_definition_history_definition_id", "element_definition_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_definition_id: Mapped[int] = mapped_column(
        ForeignKey("element_definition.id", ondelete="CASCADE"), nullable=False)
    element_key: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    definition_is_ai: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    business_name: Mapped[str | None] = mapped_column(Text)
    business_name_is_ai: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    submitted_by: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class DatasetStory(Base):
    """The plain-language story of one dataset (govern-pg-c1-element-content-build).

    One row per ``dataset_key`` (``source|schema|table``). ``data_grain`` -- what a single row of
    the dataset represents -- is its own named field here, rather than the incidental ``tagline``
    sidecar it was in the YAML store (user decision 2026-08-15). NO history table: a history
    window needs a real business event to open it, and unlike a column's Interpretation Set there
    is no dataset-level submission action in the app to serve as one (user decision 2026-08-15 --
    revisit if a dataset-level review workflow is ever built).
    """
    __tablename__ = "dataset_story"
    __table_args__ = (Index("ix_dataset_story_key", "dataset_key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    narrative: Mapped[str | None] = mapped_column(Text)
    data_grain: Mapped[str | None] = mapped_column(Text)
    is_ai_generated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    generated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ElementAssessmentScope(Base):
    """Whether a column is assessed for data quality at all (govern-pg-c1-element-content-build).

    Its OWN table rather than columns on ``element_definition`` (user decision 2026-08-15): the
    concept is acknowledged as not yet fully thought through, so keeping it separable means it can
    be redesigned -- or left dormant -- without disturbing a column's other content. C2 migrates
    ZERO rows into it: all 22 live YAML records say ``in_scope``, which is the default, so they
    carry no information.
    """
    __tablename__ = "element_assessment_scope"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('in_scope','out_of_scope')",
            name="element_assessment_scope_scope_check",
        ),
        Index("ix_element_assessment_scope_key", "element_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="in_scope")
    scope_reason: Mapped[str | None] = mapped_column(Text)
    scoped_by: Mapped[str | None] = mapped_column(Text)
    scoped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ReferenceSet(Base):
    """A shared "master" code list, e.g. ISO 4217 Currency Codes (govern-pg-d-reference-sets).

    Hand-authored/read-only through the app for this slice -- only the column-to-set BINDING
    (``ElementReferenceBinding``) is a real write path. ``parent_set_id`` lets one set point to
    another (self-FK, ON DELETE SET NULL, same safe shape as ``term.parent_term_id``) -- the
    user's own requirement, not present in the legacy YAML at all.
    """
    __tablename__ = "reference_set"
    __table_args__ = (
        CheckConstraint("kind IN ('standard','local')", name="reference_set_kind_check"),
        CheckConstraint(
            "status IN ('approved','candidate','under_review')",
            name="reference_set_status_check",
        ),
        Index("ix_reference_set_parent", "parent_set_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    set_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="local")
    standard_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="candidate")
    parent_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("reference_set.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ReferenceSetEntry(Base):
    """One code inside a `ReferenceSet`, e.g. "USD = US Dollar" (govern-pg-d-reference-sets)."""
    __tablename__ = "reference_set_entry"
    __table_args__ = (
        CheckConstraint("status IN ('active','deprecated')", name="reference_set_entry_status_check"),
        UniqueConstraint("reference_set_id", "code", name="ux_reference_set_entry_code"),
        Index("ix_reference_set_entry_set", "reference_set_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reference_set_id: Mapped[int] = mapped_column(
        ForeignKey("reference_set.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    meaning: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    aliases: Mapped[list | None] = mapped_column(JSONB)
    effective_from: Mapped[date | None] = mapped_column()
    effective_to: Mapped[date | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class ElementReferenceBinding(Base):
    """Records that a column is BOUND to a `ReferenceSet` (govern-pg-d-reference-sets).

    Replaces the `refdata_bound_set_id` note that lived inside `element_states.yaml`'s
    `metadata` section -- the only piece of the legacy binding concept, moved to its own table
    since Slice D is what finally gives shared reference sets a proper Postgres home.
    `bound_set_id` is deliberately named for the binding concept (not a generic `reference_set_id`
    ownership FK) -- user feedback 2026-08-16, fixed before any real data existed.
    """
    __tablename__ = "element_reference_binding"
    __table_args__ = (Index("ix_element_reference_binding_set", "bound_set_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bound_set_id: Mapped[int] = mapped_column(
        ForeignKey("reference_set.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class CatalogTableAnnotation(Base):
    """A user/AI-authored description + mapping note for one whole table (govern-pg-e-annotations).

    One row per ``dataset_key`` (``source|schema|table``), same key shape as ``DatasetStory``.
    No history table -- an edit overwrites in place, exactly like the YAML overlay file does
    today; annotations have no submission/review workflow of their own.
    """
    __tablename__ = "catalog_table_annotation"
    __table_args__ = (Index("ix_catalog_table_annotation_key", "dataset_key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_description: Mapped[str | None] = mapped_column(Text)
    mapping_instructions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class CatalogColumnAnnotation(Base):
    """A user/AI-authored description + mapping note for one column (govern-pg-e-annotations).

    One row per ``element_key`` (``source|schema|table|column``), same key shape as
    ``ElementDefinition``. No history table, same reasoning as ``CatalogTableAnnotation``.
    """
    __tablename__ = "catalog_column_annotation"
    __table_args__ = (Index("ix_catalog_column_annotation_key", "element_key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_description: Mapped[str | None] = mapped_column(Text)
    mapping_instructions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


