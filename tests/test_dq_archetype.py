"""Tests for core.dq_archetype — F1 archetype precedence (0a → 0b → heuristics)."""
from __future__ import annotations

from core.dq_archetype import detect_archetype
from core.dq_config import DQScoringConfig

CONFIG = DQScoringConfig.from_project()


def test_declared_pk_is_key_like_0a():
    col = {"name": "id", "data_type": "VARCHAR", "is_primary_key": True, "distinct_count": 10}
    archetype, reason = detect_archetype(col, None, None, CONFIG)
    assert archetype == "key_like"
    assert reason.startswith("0a")


def test_inferred_pk_via_table_is_key_like_0a():
    col = {"name": "account_id", "data_type": "BIGINT", "distinct_count": 5}
    tbl = {"inferred_primary_key": ["account_id"]}
    archetype, _ = detect_archetype(col, tbl, None, CONFIG)
    assert archetype == "key_like"


def test_accepted_semantic_type_overrides_heuristic_0b():
    # 30-distinct numeric would be 'coded' by heuristic; accepted 'rate' → numeric.
    col = {"name": "interest_rate", "data_type": "DECIMAL", "distinct_count": 30}
    record = {"accepted_at": "2026-08-20T00:00:00Z", "type_id": "rate"}
    archetype, reason = detect_archetype(col, None, record, CONFIG)
    assert archetype == "numeric"
    assert reason.startswith("0b")


def test_unaccepted_semantic_type_does_not_drive_archetype():
    col = {"name": "interest_rate", "data_type": "DECIMAL", "distinct_count": 30}
    record = {"type_id": "rate"}
    archetype, _ = detect_archetype(col, None, record, CONFIG)
    assert archetype == "coded"  # falls back to heuristic (distinct <= 50)


def test_accepted_identifier_is_key_like():
    col = {"name": "cpty", "data_type": "VARCHAR", "distinct_count": 9000, "uniqueness_pct": 0.9}
    record = {"accepted_at": "2026-08-20T00:00:00Z", "type_id": "identifier"}
    archetype, _ = detect_archetype(col, None, record, CONFIG)
    assert archetype == "key_like"


def test_heuristic_key_like_by_uniqueness():
    col = {"name": "ref", "data_type": "VARCHAR", "distinct_count": 9999,
           "uniqueness_pct": 0.999, "row_count": 10000}
    archetype, reason = detect_archetype(col, None, None, CONFIG)
    assert archetype == "key_like"
    assert reason.startswith("1")


def test_coded_by_low_cardinality():
    col = {"name": "country", "data_type": "VARCHAR", "distinct_count": 24, "uniqueness_pct": 0.002}
    archetype, _ = detect_archetype(col, None, None, CONFIG)
    assert archetype == "coded"


def test_numeric_declared_type():
    col = {"name": "amount", "data_type": "DECIMAL", "distinct_count": 8000, "uniqueness_pct": 0.8}
    archetype, _ = detect_archetype(col, None, None, CONFIG)
    assert archetype == "numeric"


def test_date_declared_type():
    col = {"name": "d", "data_type": "DATE", "distinct_count": 5000, "uniqueness_pct": 0.5}
    archetype, _ = detect_archetype(col, None, None, CONFIG)
    assert archetype == "date"


def test_text_with_reliable_pattern():
    col = {"name": "iban", "data_type": "VARCHAR", "distinct_count": 9000, "uniqueness_pct": 0.9,
           "inferred_pattern": "IBAN", "pattern_confidence": 0.97}
    archetype, _ = detect_archetype(col, None, None, CONFIG)
    assert archetype == "text"


def test_free_text_default():
    col = {"name": "notes", "data_type": "VARCHAR", "distinct_count": 9000, "uniqueness_pct": 0.9}
    archetype, reason = detect_archetype(col, None, None, CONFIG)
    assert archetype == "free_text"
    assert reason.startswith("6")
