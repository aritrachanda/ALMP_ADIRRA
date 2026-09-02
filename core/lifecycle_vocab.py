"""Canonical lifecycle vocabulary — the single source of truth (Phase 5b.3.0).

One status vocabulary shared by the three governed items — the **Interpretation set**
(``core.lifecycle`` / ``element_lifecycle_repo``), the **Reference Codeset**
(``reference_code_repo``) and the **Business Glossary** (``glossary_db.status``).

Design rules:
  * The stored backend value **is** the UI label's slug (e.g. the DB stores ``in_review``
    and the UI renders "In-Review"), so a value read straight from the database is
    self-explanatory when digging manually.
  * No item is forced to use every state — each declares its applicable subset below.
  * ``withdrawn`` / ``revoked`` are **transition-only actions**: they never rest as a
    subject's status. A Withdraw or Revoke returns the subject to an editable ``draft``
    and survives only as a ``lifecycle_transition`` audit row.

Empty vs Draft (D4): a Save lands on ``empty`` when only the identifier/title exists and
no other content, else ``draft``. Interpretation/reference-code titles are auto-provided
(so it is a pure content check); a glossary term is title-only when first created.
"""
from __future__ import annotations

# ── Canonical values (backend == UI slug), in lifecycle order ────────────────
EMPTY = "empty"
DRAFT = "draft"
IN_REVIEW = "in_review"
APPROVED = "approved"
RETURNED = "returned"
REJECTED = "rejected"
DEPRECATED = "deprecated"
WITHDRAWN = "withdrawn"
REVOKED = "revoked"

CANONICAL_STATUSES: tuple[str, ...] = (
    EMPTY,
    DRAFT,
    IN_REVIEW,
    APPROVED,
    RETURNED,
    REJECTED,
    DEPRECATED,
    WITHDRAWN,
    REVOKED,
)

#: UI label per canonical value (backend value ⇒ display label).
STATUS_LABELS: dict[str, str] = {
    EMPTY: "Empty",
    DRAFT: "Draft",
    IN_REVIEW: "In-Review",
    APPROVED: "Approved",
    RETURNED: "Returned",
    REJECTED: "Rejected",
    DEPRECATED: "Deprecated",
    WITHDRAWN: "Withdrawn",
    REVOKED: "Revoked",
}

# ── Kind classification ──────────────────────────────────────────────────────
#: Actions that leave NO distinct resting status — they live only in the audit trail;
#: the subject folds back to an editable ``draft``.
TRANSITION_ONLY_STATUSES: frozenset[str] = frozenset({WITHDRAWN, REVOKED})
#: Statuses a subject may actually REST in (a valid stored current status).
RESTING_STATUSES: frozenset[str] = frozenset(CANONICAL_STATUSES) - TRANSITION_ONLY_STATUSES
#: The only status that counts as fully approved (DQ-serving / version-serving rule).
APPROVED_STATUSES: frozenset[str] = frozenset({APPROVED})

# ── Per-item applicability (resting states each store uses) ───────────────────
INTERPRETATION_STATUSES: frozenset[str] = frozenset(
    {EMPTY, DRAFT, IN_REVIEW, APPROVED, RETURNED, REJECTED}
)
REFERENCE_CODE_STATUSES: frozenset[str] = frozenset(
    {EMPTY, DRAFT, IN_REVIEW, APPROVED, RETURNED, REJECTED}
)
GLOSSARY_STATUSES: frozenset[str] = frozenset(
    {EMPTY, DRAFT, IN_REVIEW, APPROVED, DEPRECATED, REJECTED}
)


def label(status: str | None) -> str:
    """Return the display label for a canonical status (falls back to Title Case)."""
    if not status:
        return "Unknown"
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def derive_saved_state(has_content: bool) -> str:
    """The D4 Empty-vs-Draft rule: ``draft`` when any real content exists, else ``empty``."""
    return DRAFT if has_content else EMPTY
