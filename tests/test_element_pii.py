"""Unit tests for the element PII flag helper (5b.3.2 PII surfacing).

A column is PII by either signal: the governed semantic type (vocabulary
``is_pii``) or the profiler's value-pattern (``inferred_pattern == 'PII'``).
"""
from api.routes.element import _column_pii, _column_pii_category


def test_semantic_pii_flags_column():
    assert _column_pii({"pii": True, "pii_category": "contact"}, {}) is True
    assert _column_pii_category({"pii": True, "pii_category": "contact"}, {}) == "contact"


def test_profiler_pattern_flags_column():
    assert _column_pii({}, {"inferred_pattern": "PII"}) is True
    assert _column_pii_category({}, {"inferred_pattern": "PII"}) == "personal_identity"


def test_non_pii_column():
    assert _column_pii({"pii": False}, {"inferred_pattern": "IBAN"}) is False
    assert _column_pii_category({"pii": False}, {"inferred_pattern": "IBAN"}) is None


def test_none_inputs_are_safe():
    assert _column_pii(None, None) is False
    assert _column_pii_category(None, None) is None


def test_semantic_category_wins_over_profiler_default():
    record = {"pii": True, "pii_category": "financial_account"}
    assert _column_pii_category(record, {"inferred_pattern": "PII"}) == "financial_account"


def test_business_id_pattern_never_flags_pii():
    """A profiler-detected business ID (Y-Tunnus) is a distinct pattern name from PII
    (Henkilotunnus) — it must never be eligible for the PII badge, regardless of the
    semantic-type record (detected, proposed, confirmed, or absent entirely)."""
    assert _column_pii({}, {"inferred_pattern": "BUSINESS_ID"}) is False
    assert _column_pii_category({}, {"inferred_pattern": "BUSINESS_ID"}) is None
    assert _column_pii({"pii": False}, {"inferred_pattern": "BUSINESS_ID"}) is False

