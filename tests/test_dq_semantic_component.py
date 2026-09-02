"""Tests for the Semantic Type line-item folded into Interpretation — SD-R3c (F3).

The Semantic Type used to be a 4th DQ component (U6a/U6b); SD-R3c retires that
component and re-homes its scoring as a line-item INSIDE the Interpretation
component (renamed from Definition). The scoring logic is unchanged — a stepped
scale × a 7-point max, minus a type/value-conflict deduction, floored at 0
— only WHERE its points live changed. These tests prove the line-item scores
correctly and that Interpretation's four line-items sum natively to its weight.

2026-08-20 (tech-debt #13/#36/#45): there is no persisted disposition word
anymore — the bucket is derived from ``type_id``/``accepted_at``/``confidence``.
The test helper below still speaks in the old accepted/proposed/suggested/
unresolved vocabulary (clearest for the reader) but builds records shaped the
new way.
"""
from __future__ import annotations

from core.dq_config import DQScoringConfig
from core.dq_scorer import score_column

CONFIG = DQScoringConfig.from_project()          # the shipped 3-component fold


def _component(breakdown, name):
    return next((c for c in breakdown["components"] if c["name"] == name), None)


def _semantic_item(breakdown):
    interp = _component(breakdown, "interpretation")
    return next((li for li in interp["line_items"] if li["label"] == "Semantic Type"), None)


def _sem(disposition, *, type_id="country_code", conflict=False, tier=1, source="rule"):
    rec = {"type_id": type_id, "tier": tier, "source": source, "type_value_conflict": conflict}
    if disposition == "accepted":
        rec["accepted_at"] = "2026-08-20T00:00:00Z"
        rec["confidence"] = 0.95
    elif disposition == "proposed":
        rec["confidence"] = 0.70  # >= floor_threshold (0.60), not yet accepted
    elif disposition == "suggested":
        rec["confidence"] = 0.50  # < floor_threshold, not yet accepted
    elif disposition == "unresolved":
        rec["type_id"] = "unresolved"
        rec["confidence"] = 0.0
    return rec


def _col_a():
    return {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }


def _score_a(semantic_record=None):
    return score_column(
        col_dict=_col_a(),
        semantic_record=semantic_record,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )


def _col_b():
    return {
        "name": "exposure_amount", "data_type": "DECIMAL",
        "row_count": 10000, "null_count": 50, "distinct_count": 8000, "uniqueness_pct": 0.8,
        "empty_string_count": 0, "placeholder_count": 0, "type_mismatch_count": 0,
        "invalid_format_count": None, "suspicious_date_count": 0, "future_date_count": 0,
        "numeric_stddev": 84210.0, "numeric_avg": 152300.0, "numeric_median": 141800.0,
        "numeric_outlier_count": 40, "outlier_detection": "two_sided",
        "top_values": [{"value": "1000", "count": 300}], "constant_run_warning": False,
    }


def _score_b(semantic_record=None):
    return score_column(
        col_dict=_col_b(),
        semantic_record=semantic_record,
        definition={"present": True, "is_ai": True, "lifecycle": "defined"},
        business_name={"value": "exposure_amount", "source": "ai_or_auto"},
        glossary={"linked": False},
        config=CONFIG,
    )


# ═══ Semantic Type lives inside Interpretation, never as its own component ════

def test_no_standalone_semantic_component():
    breakdown = _score_a(semantic_record=_sem("accepted"))
    assert _component(breakdown, "semantic") is None
    assert "semantic" not in breakdown["applicable_components"]


def test_semantic_type_is_an_interpretation_line_item():
    breakdown = _score_a(semantic_record=_sem("accepted"))
    interp = _component(breakdown, "interpretation")
    labels = [li["label"] for li in interp["line_items"]]
    assert labels == ["Definition", "Business Name", "Glossary Linkage", "Semantic Type"]


def test_interpretation_line_items_sum_natively_to_block():
    breakdown = _score_a(semantic_record=_sem("accepted"))
    interp = _component(breakdown, "interpretation")
    assert interp["base_max"] == 30.0
    assert sum(li["max"] for li in interp["line_items"]) == 30
    assert interp["earned"] == sum(li["earned"] for li in interp["line_items"])


# ═══ Stepped scale × 7-point max (unchanged logic, new home) ═════════════════

def _semantic_earned(disposition, *, conflict=False):
    return _semantic_item(_score_a(semantic_record=_sem(disposition, conflict=conflict)))["earned"]


def test_semantic_accepted_is_full():
    assert _semantic_earned("accepted") == 7.0        # 7 × 1.0


def test_semantic_proposed_is_partial():
    assert _semantic_earned("proposed") == 3.5         # 7 × 0.5


def test_semantic_suggested_is_low():
    assert _semantic_earned("suggested") == 1.4        # 7 × 0.2


def test_semantic_unresolved_is_zero():
    assert _semantic_earned("unresolved") == 0.0


def test_semantic_unresolved_type_id_overrides_disposition():
    # An accepted disposition on an 'unresolved' type earns nothing (no governed meaning).
    breakdown = _score_a(semantic_record=_sem("accepted", type_id="unresolved"))
    assert _semantic_item(breakdown)["earned"] == 0.0


def test_semantic_conflict_deduction():
    # accepted 7 − (7 × 0.3 = 2.1) = 4.9
    assert _semantic_earned("accepted", conflict=True) == 4.9
    # proposed 3.5 − 2.1 = 1.4
    assert _semantic_earned("proposed", conflict=True) == 1.4


def test_semantic_line_item_present_without_record():
    # No resolver record → the Semantic Type line-item still exists, scoring 0/7.
    breakdown = _score_a(semantic_record=None)
    item = _semantic_item(breakdown)
    assert item is not None
    assert item["earned"] == 0.0
    assert item["max"] == 7.0


def test_semantic_carries_f3_evidence():
    breakdown = _score_a(semantic_record=_sem("accepted", tier=2, source="ai"))
    item = _semantic_item(breakdown)
    assert item["evidence"]["accepted"] is True
    assert item["evidence"]["tier"] == 2
    assert item["evidence"]["source"] == "ai"
    assert item["evidence"]["type_value_conflict"] is False


# ═══ Worked examples with the folded line-item (SD-R3c numbers) ══════════════

def test_worked_example_a_fully_governed_is_81():
    """Coded column, accepted country_code semantic → a fully-governed column.

    Profile        39.2 / 50
    Interpretation 11 + 5 + 5 + 7 = 28.0 / 30   (Def · BN · Glossary · Semantic)
    Reference Data 9 + 5           = 14.0 / 20
    ─────────────────────────────────────
    Σ base = 100 → factor 1.0
    DQ = 39.2 + 28.0 + 14.0 = 81.2 → 81 · Good
    """
    breakdown = _score_a(semantic_record=_sem("accepted"))
    assert breakdown["applicable_components"] == ["profile", "interpretation", "reference_data"]
    assert breakdown["reallocation_factor"] == 1.0
    assert _component(breakdown, "interpretation")["earned"] == 28.0
    assert _semantic_item(breakdown)["earned"] == 7.0
    assert breakdown["dq_score"] == 81
    assert breakdown["grade_label"] == "Good"


def test_worked_example_b_numeric_reallocation_accepted_is_79():
    """Numeric column, no reference data, accepted monetary_amount semantic.

    Profile        48.3 / 50
    Interpretation 6 + 2 + 0 + 7 = 15.0 / 30
    ─────────────────────────────────────
    Σ base = 80 → factor 1.25
    DQ = (48.3 + 15.0) × 1.25 = 63.3 × 1.25 = 79.13 → 79 · Good
    """
    breakdown = _score_b(semantic_record=_sem("accepted", type_id="monetary_amount"))
    assert breakdown["applicable_components"] == ["profile", "interpretation"]
    assert breakdown["reallocation_factor"] == 1.25
    assert _component(breakdown, "interpretation")["earned"] == 15.0
    assert breakdown["dq_score"] == 79
    assert breakdown["grade_label"] == "Good"


# ═══ Remediation for a Semantic Type gap points at the Interpretation tab ═════

def test_semantic_gap_emits_accept_action_on_interpretation_tab():
    breakdown = _score_a(semantic_record=_sem("proposed"))
    sem_actions = [a for a in breakdown.get("actions", []) if a.get("line_item") == "Semantic Type"]
    assert len(sem_actions) == 1
    action = sem_actions[0]
    assert action["component"] == "interpretation"
    assert action["action_type"] == "governance"
    assert action["points"] > 0
    assert "Interpretation tab" in action["step"]
    assert "Semantic Deduction" not in action["step"]
    assert action.get("resulting_score") is not None


def test_accepted_semantic_emits_no_action():
    breakdown = _score_a(semantic_record=_sem("accepted"))
    assert all(a.get("line_item") != "Semantic Type" for a in breakdown.get("actions", []))


def test_semantic_action_gain_does_not_overshoot_100():
    # A proposed type on an otherwise strong column: the advertised destination
    # must never exceed 100 (the native-scale fix — no reweight double factor).
    breakdown = _score_a(semantic_record=_sem("proposed"))
    for action in breakdown.get("actions", []):
        assert action["resulting_score"] <= 100
