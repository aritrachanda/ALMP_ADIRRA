"""Phase 5a — canonical governance lifecycle vocabulary + legacy derivation.

Proves the old-element-state → new-status mapping is value-preserving w.r.t. DQ scoring:
the only intended movements are draft-with-content → saved and submitted-undecided →
in_review (both a +1 lifecycle tick, documented in 05-impact-analysis.md).
"""
from __future__ import annotations

from core import lifecycle as lc


# ── Vocabulary invariants ────────────────────────────────────────────────────

def test_canonical_statuses_are_labelled():
    # STATUS_LABELS is the shared superset (includes glossary-only 'deprecated'); it must
    # cover every interpretation status.
    assert set(lc.CANONICAL_STATUSES) <= set(lc.STATUS_LABELS)


def test_groupings_partition_the_vocabulary():
    grouped = lc.PRESUBMIT_STATUSES | lc.UNDER_REVIEW_STATUSES | lc.REVIEWED_STATUSES
    assert grouped == set(lc.CANONICAL_STATUSES)
    # groups are mutually exclusive
    assert not (lc.PRESUBMIT_STATUSES & lc.UNDER_REVIEW_STATUSES)
    assert not (lc.UNDER_REVIEW_STATUSES & lc.REVIEWED_STATUSES)
    assert not (lc.PRESUBMIT_STATUSES & lc.REVIEWED_STATUSES)


def test_only_approved_counts_as_approved():
    assert lc.APPROVED_STATUSES == {"approved"}


def test_resting_and_transition_only_partition_the_vocabulary():
    assert lc.RESTING_STATUSES | lc.TRANSITION_ONLY_STATUSES == set(lc.CANONICAL_STATUSES)
    assert not (lc.RESTING_STATUSES & lc.TRANSITION_ONLY_STATUSES)
    # withdrawn/revoked never rest — they resolve to 'draft'
    assert lc.TRANSITION_ONLY_STATUSES == {"withdrawn", "revoked"}


def test_locked_statuses_are_not_editable():
    # approved + in_review are the two locked states (need revoke / withdraw first)
    assert "approved" not in lc.EDITABLE_STATUSES
    assert "in_review" not in lc.EDITABLE_STATUSES
    # every other status is editable
    assert lc.EDITABLE_STATUSES == set(lc.CANONICAL_STATUSES) - {"approved", "in_review"}


# ── Derivation from legacy element state + overlay ───────────────────────────

def test_blank_draft_is_empty():
    assert lc.derive_status(old_state="draft", has_content=False,
                            submitted=False, decision=None) == "empty"
    assert lc.derive_status(old_state=None, has_content=False,
                            submitted=False, decision=None) == "empty"


def test_draft_with_content_becomes_draft():
    # intended +1 tick (legacy draft lifecycle 1 → canonical draft 2)
    assert lc.derive_status(old_state="draft", has_content=True,
                            submitted=False, decision=None) == "draft"


def test_defined_is_draft():
    # neutral: legacy 'defined' (2) → 'draft' (2)
    assert lc.derive_status(old_state="defined", has_content=True,
                            submitted=False, decision=None) == "draft"


def test_submitted_undecided_is_in_review():
    # intended +1 tick (defined 2 → in_review 3)
    assert lc.derive_status(old_state="defined", has_content=True,
                            submitted=True, decision=None) == "in_review"


def test_approved_decision_is_approved():
    assert lc.derive_status(old_state="approved", has_content=True,
                            submitted=True, decision="approved") == "approved"
    # even without the state flag, an approved decision wins
    assert lc.derive_status(old_state="defined", has_content=True,
                            submitted=True, decision="approved") == "approved"


def test_rejected_decision_maps_to_returned():
    # locked decision: legacy 'rejected' → new 'returned' (not the new 'rejected')
    assert lc.derive_status(old_state="defined", has_content=True,
                            submitted=True, decision="rejected") == "returned"


def test_returned_is_score_equivalent_to_draft():
    # both rest at the same point band (2) — neutral for parity
    returned = lc.derive_status(old_state="defined", has_content=True,
                               submitted=True, decision="rejected")
    draft = lc.derive_status(old_state="defined", has_content=True,
                            submitted=False, decision=None)
    assert returned == "returned" and draft == "draft"
