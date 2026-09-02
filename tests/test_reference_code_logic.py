"""Phase 5b.2 — pure derivation logic for per-code Reference Data (no database)."""
from __future__ import annotations

from core.reference_code_repo import derive_set_status, set_badge


def _row(code, meaning, status):
    return {"code": code, "value": None, "meaning": meaning, "origin": "profiled", "status": status}


def test_derive_set_status_none_when_undocumented():
    assert derive_set_status([]) == "none"
    assert derive_set_status([_row("A", "", "empty")]) == "none"


def test_derive_set_status_all_approved_is_approved():
    rows = [_row("A", "Active", "approved"), _row("B", "Blocked", "approved")]
    assert derive_set_status(rows) == "approved"


def test_derive_set_status_any_in_review_is_under_review():
    rows = [_row("A", "Active", "approved"), _row("B", "Blocked", "in_review")]
    assert derive_set_status(rows) == "under_review"


def test_derive_set_status_only_drafts_is_candidate():
    rows = [_row("A", "Active", "draft"), _row("B", "Blocked", "draft")]
    assert derive_set_status(rows) == "candidate"


def test_derive_ignores_undocumented_rows():
    # An empty/undocumented row does not drag an otherwise-approved set down.
    rows = [_row("A", "Active", "approved"), _row("B", "", "empty")]
    assert derive_set_status(rows) == "approved"


def test_set_badge_partially_approved_until_100pct():
    rows = [_row("A", "Active", "approved"), _row("B", "Blocked", "draft")]
    assert set_badge(rows) == "partially_approved"


def test_set_badge_approved_at_100pct():
    rows = [_row("A", "Active", "approved"), _row("B", "Blocked", "approved")]
    assert set_badge(rows) == "approved"


def test_set_badge_in_review_when_submitted_none_approved():
    rows = [_row("A", "Active", "in_review"), _row("B", "Blocked", "draft")]
    assert set_badge(rows) == "in_review"


def test_set_badge_draft_and_empty():
    assert set_badge([_row("A", "Active", "draft")]) == "draft"
    assert set_badge([_row("A", "", "empty")]) == "empty"
    assert set_badge([]) == "empty"
