"""Shared ORM models package (S0 models split).

Single home for every table's SQLAlchemy model, split by feature into sibling modules
(``glossary.py``, ``governance.py``, ``audit.py``, ``catalog.py``) but sharing ONE ``Base`` /
metadata object defined in ``base.py``. Import everything from this package
(``from core.shared.models import Term, CatalogSource, ...``) rather than reaching into an
individual feature module directly — this is what lets ``db/migrations/env.py`` see every
table via a single import for autogenerate.

Connection layer (engine/session/health check) stays in ``core.glossary_db.db`` for now —
moving it is deferred to the retirement slice (see openspec/changes/govern-pg-s0-foundations).
"""
from __future__ import annotations

from core.shared.models.audit import AuditEvent
from core.shared.models.base import Base
from core.shared.models.catalog import (
    CatalogDataset,
    CatalogDatasetSnapshot,
    CatalogElement,
    CatalogElementSnapshot,
    CatalogRefreshEvent,
    CatalogSource,
)
from core.shared.models.glossary import (
    Glossary,
    GlossaryGroupMeta,
    Linkage,
    LinkageTriage,
    Term,
    TermRelation,
    TermVersion,
)
from core.shared.models.governance import (
    CatalogColumnAnnotation,
    CatalogTableAnnotation,
    DatasetStory,
    DqScore,
    DqScoreHistory,
    ElementAssessmentScope,
    ElementDefinition,
    ElementDefinitionHistory,
    ElementReferenceBinding,
    LifecycleTransition,
    ReferenceCode,
    ReferenceCodeHistory,
    ReferenceSet,
    ReferenceSetEntry,
    ReviewSubject,
    ReviewTask,
    SemanticTypeAssignment,
    SemanticTypeAssignmentHistory,
)

__all__ = [
    "Base",
    "Glossary",
    "Term",
    "TermVersion",
    "TermRelation",
    "Linkage",
    "LinkageTriage",
    "GlossaryGroupMeta",
    "LifecycleTransition",
    "ReviewSubject",
    "ReviewTask",
    "ReferenceCode",
    "ReferenceCodeHistory",
    "DqScore",
    "DqScoreHistory",
    "SemanticTypeAssignment",
    "SemanticTypeAssignmentHistory",
    "ElementDefinition",
    "ElementDefinitionHistory",
    "DatasetStory",
    "ElementAssessmentScope",
    "ReferenceSet",
    "ReferenceSetEntry",
    "ElementReferenceBinding",
    "CatalogTableAnnotation",
    "CatalogColumnAnnotation",
    "AuditEvent",
    "CatalogSource",
    "CatalogDataset",
    "CatalogElement",
    "CatalogRefreshEvent",
    "CatalogDatasetSnapshot",
    "CatalogElementSnapshot",
]
