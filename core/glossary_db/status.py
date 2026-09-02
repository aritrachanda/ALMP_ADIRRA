"""Canonical glossary term-status vocabulary — the single source of truth.

Retirement-gate #4 requires the status enum to be pinned in one place. The database
mirrors this in the ``term_status_check`` CHECK constraint (migration 0001); the ORM,
repository validation and every scoring consumer import from here so the vocabulary is
defined once.

Canonical lifecycle (Phase 1 decision D3): ``draft → in_review → approved`` with
``deprecated`` / ``rejected`` as terminal off-ramps. ``confirmed`` / ``published`` are
legacy values that are never written under the canonical enum but are still accepted by
the "confirmed" scoring set so a stray legacy row scores as it always did.
"""
from __future__ import annotations

#: Every valid term status, in lifecycle order.
CANONICAL_STATUSES: tuple[str, ...] = (
    "empty",
    "draft",
    "in_review",
    "approved",
    "deprecated",
    "rejected",
)

#: Statuses that count as steward-confirmed for DQ scoring / element detail. Only
#: ``approved`` is canonical; the legacy aliases are kept for backward compatibility
#: (they are never produced by the v2 store, so including them changes no live score).
_LEGACY_CONFIRMED: frozenset[str] = frozenset({"confirmed", "published"})
CONFIRMED_STATUSES: frozenset[str] = frozenset({"approved"}) | _LEGACY_CONFIRMED
