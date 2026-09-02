"""Backwards-compatible re-export shim (S0 models split, 2026-08-10).

Every model class that used to live in this module has moved to ``core.shared.models``,
split by feature (``glossary.py``/``governance.py``/``audit.py``/``catalog.py``), sharing one
``Base``. This module now just re-exports them so any import that was missed during the
in-repo repoint still resolves. New code should import directly from ``core.shared.models``.
"""
from __future__ import annotations

from core.shared.models import (
    AuditEvent,
    Base,
    CatalogDataset,
    CatalogDatasetSnapshot,
    CatalogElement,
    CatalogElementSnapshot,
    CatalogRefreshEvent,
    CatalogSource,
    Glossary,
    GlossaryGroupMeta,
    Linkage,
    LinkageTriage,
    LifecycleTransition,
    ReferenceCode,
    ReviewSubject,
    ReviewTask,
    Term,
    TermRelation,
    TermVersion,
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
    "AuditEvent",
    "CatalogSource",
    "CatalogDataset",
    "CatalogElement",
    "CatalogRefreshEvent",
    "CatalogDatasetSnapshot",
    "CatalogElementSnapshot",
]
