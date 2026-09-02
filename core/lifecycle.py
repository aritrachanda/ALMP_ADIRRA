"""Canonical governance lifecycle vocabulary (Phase 5a).

Subject-agnostic: the SAME status set governs a Data Element Interpretation Set and a
Business Glossary Term (the two review subjects agreed in the Phase 5 planning). This
module owns only the *vocabulary*, the *groupings*, and the *derivation* from the legacy
element states — it deliberately does NOT own the DQ point values. Those live in
``governance/dq_scoring_config.yaml`` (``definition_scales.description.lifecycle``) so the
scorer keeps a single source of truth; see docs/architecture/Glossary Rebuild/reports/
05-impact-analysis.md.

Status ladder (single lifecycle for the whole interpretation set, one reviewer = steward):

    empty  → draft → in_review → approved                (the happy path)
                      ↕ withdrawn                         (analyst pulls a submission back)
                        → returned / rejected             (steward decision)
    approved → revoked → draft                            (revoke-to-edit; prior version serves)

Design notes:
- ``approved`` and ``in_review`` are LOCKED (not directly editable): editing an approved
  subject requires a Revoke first; an in-review subject requires a Withdraw first.
- Any bounce-back (withdrawn / returned / rejected / revoked) rests as an *editable* state,
  equivalent to ``draft`` for scoring, until re-submitted.
- ``approved`` is the ONLY status that counts as "fully approved" for DQ-serving and for the
  "prior approved version keeps serving" rule.
"""
from __future__ import annotations

from typing import Literal

from core.lifecycle_vocab import (
    APPROVED,
    APPROVED_STATUSES,
    DRAFT,
    EMPTY,
    IN_REVIEW,
    REJECTED,
    RETURNED,
    REVOKED,
    STATUS_LABELS,
    TRANSITION_ONLY_STATUSES,
    WITHDRAWN,
)

# ── Canonical vocabulary (sourced from core.lifecycle_vocab) ─────────────────
#: The interpretation-set subset of the shared vocabulary (no ``deprecated`` — that is
#: glossary-only). ``STATUS_LABELS`` / ``APPROVED_STATUSES`` / ``TRANSITION_ONLY_STATUSES``
#: are imported from the shared module so the terms are defined exactly once.
CANONICAL_STATUSES: tuple[str, ...] = (
    EMPTY,
    DRAFT,
    IN_REVIEW,
    APPROVED,
    WITHDRAWN,
    RETURNED,
    REJECTED,
    REVOKED,
)
GovernanceStatus = Literal[
    "empty", "draft", "in_review", "approved",
    "withdrawn", "returned", "rejected", "revoked",
]

# ── Groupings (drive the UI grouping + workflow rules) ───────────────────────
PRESUBMIT_STATUSES = frozenset({EMPTY, DRAFT})
UNDER_REVIEW_STATUSES = frozenset({IN_REVIEW, WITHDRAWN})
REVIEWED_STATUSES = frozenset({APPROVED, RETURNED, REJECTED, REVOKED})

#: Statuses whose subject is directly editable (NOT locked). ``approved`` and
#: ``in_review`` are excluded — they must be revoked / withdrawn first.
EDITABLE_STATUSES = frozenset(
    {EMPTY, DRAFT, WITHDRAWN, RETURNED, REJECTED, REVOKED}
)

#: Statuses that are open work in a review queue (steward's inbox).
OPEN_REVIEW_STATUSES = frozenset({IN_REVIEW})

#: Statuses a subject may REST in (a valid ``review_subject.current_state``).
RESTING_STATUSES = frozenset(
    {EMPTY, DRAFT, IN_REVIEW, APPROVED, RETURNED, REJECTED}
)

# ── Legacy element states (pre-Phase-5) ──────────────────────────────────────
#: Old ``core.element_state`` vocabulary, kept only for migration/derivation.
LEGACY_ELEMENT_STATES = ("draft", "defined", "approved")


def derive_status(
    *,
    old_state: str | None,
    has_content: bool,
    submitted: bool,
    decision: str | None,
) -> str:
    """Map a legacy element (state + submission overlay) to a canonical status.

    Value-preserving w.r.t. DQ scoring — see the remap table in the Phase-5 impact
    analysis. The only intended score movements this produces are:
      * a legacy ``draft`` row that already has content → ``draft`` (lifecycle 1 → 2), and
      * a submitted-but-undecided row → ``in_review`` (lifecycle 2 → 3).
    Everything else lands on a status whose points equal the legacy points.

    Inputs (all derivable from ``element_states.yaml``):
      old_state  — legacy 'draft' | 'defined' | 'approved' (or None → 'draft').
      has_content — a description (or business name) exists for the element.
      submitted  — the submission overlay has ``submitted_at`` set.
      decision   — overlay decision: 'approved' | 'rejected' | None.
    """
    # A recorded decision wins — it reflects the last steward action.
    if decision == "approved" or old_state == "approved":
        return "approved"
    if decision == "rejected":
        # Locked decision (2026-07-25): legacy 'rejected' maps to the new 'returned'
        # (fix-and-resubmit), NOT the new outright 'rejected'.
        return "returned"
    # Submitted and awaiting a decision.
    if submitted:
        return "in_review"
    # Not submitted: content present → draft; otherwise a blank shell → empty.
    if has_content:
        return DRAFT
    return EMPTY
