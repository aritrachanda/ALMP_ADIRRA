"""Tests for core.dq_scorer — components, reallocation, grade bands.

The two worked examples (A: coded, B: numeric/reallocation) assert the EXACT
component and composite numbers of the SD-R3c model: Profile 50 / Interpretation
30 / Reference Data 20, with Semantic Type folded into Interpretation as a
line-item. These supersede the old 4-component numbers (81/73) — with no
resolver record the Semantic Type line-item scores 0/7, so both examples move.
"""
from __future__ import annotations

from core.dq_config import DQScoringConfig
from core.dq_scorer import grade_for, score_column

# The shipped config IS the 3-component fold (SD-R3c). No flag to toggle.
CONFIG = DQScoringConfig.from_project()


def _component(breakdown, name):
    return next(c for c in breakdown["components"] if c["name"] == name)


def _line_item(component, label):
    return next(li for li in component["line_items"] if li["label"] == label)


# ── Worked example A — coded column, all three components → 74 (SD-R3c) ───────

def test_worked_example_a_coded_column():
    col = {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }
    breakdown = score_column(
        col_dict=col,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )

    assert breakdown["archetype"] == "coded"
    profile = _component(breakdown, "profile")
    assert _line_item(profile, "Completeness")["earned"] == 14.0
    assert _line_item(profile, "Validity")["earned"] == 11.2
    assert _line_item(profile, "Consistency")["earned"] == 6.0
    assert _line_item(profile, "Findings overlay")["earned"] == 8.0
    assert profile["earned"] == 39.2

    definition = _component(breakdown, "interpretation")
    assert _line_item(definition, "Definition")["earned"] == 11.0
    assert _line_item(definition, "Business Name")["earned"] == 5.0
    assert _line_item(definition, "Glossary Linkage")["earned"] == 5.0
    assert _line_item(definition, "Semantic Type")["earned"] == 0.0
    assert definition["earned"] == 21.0

    refdata = _component(breakdown, "reference_data")
    assert _line_item(refdata, "Codes documented")["earned"] == 9.0
    assert _line_item(refdata, "Code set approved")["earned"] == 5.0
    assert refdata["earned"] == 14.0

    assert breakdown["reallocation_factor"] == 1.0
    assert breakdown["dq_score"] == 74
    assert breakdown["grade_label"] == "Adequate"


# ── Worked example B — numeric column, reallocation → 70 (SD-R3c) ─────────────

def test_worked_example_b_numeric_reallocation():
    col = {
        "name": "exposure_amount", "data_type": "DECIMAL",
        "row_count": 10000, "null_count": 50, "distinct_count": 8000, "uniqueness_pct": 0.8,
        "empty_string_count": 0, "placeholder_count": 0, "type_mismatch_count": 0,
        "invalid_format_count": None, "suspicious_date_count": 0, "future_date_count": 0,
        "numeric_stddev": 84210.0, "numeric_avg": 152300.0, "numeric_median": 141800.0,
        "numeric_outlier_count": 40, "outlier_detection": "two_sided",
        "top_values": [{"value": "1000", "count": 300}], "constant_run_warning": False,
    }
    breakdown = score_column(
        col_dict=col,
        definition={"present": True, "is_ai": True, "lifecycle": "defined"},
        business_name={"value": "exposure_amount", "source": "ai_or_auto"},
        glossary={"linked": False},
        config=CONFIG,
    )

    assert breakdown["archetype"] == "numeric"
    profile = _component(breakdown, "profile")
    assert _line_item(profile, "Completeness")["earned"] == 13.7
    assert _line_item(profile, "Validity")["earned"] == 10.0
    assert _line_item(profile, "Consistency")["earned"] == 16.6
    assert profile["earned"] == 48.3

    definition = _component(breakdown, "interpretation")
    assert _line_item(definition, "Definition")["earned"] == 6.0
    assert _line_item(definition, "Business Name")["earned"] == 2.0
    assert _line_item(definition, "Glossary Linkage")["earned"] == 0.0
    assert _line_item(definition, "Semantic Type")["earned"] == 0.0
    assert definition["earned"] == 8.0

    assert breakdown["applicable_components"] == ["profile", "interpretation"]
    assert breakdown["reallocation_factor"] == 1.25
    assert breakdown["dq_score"] == 70
    assert breakdown["grade_label"] == "Adequate"


# ── grade band lookup (§7) ───────────────────────────────────────────────────

def test_grade_bands():
    assert grade_for(95, CONFIG)["label"] == "Excellent"
    assert grade_for(80, CONFIG)["label"] == "Good"
    assert grade_for(70, CONFIG)["label"] == "Adequate"
    assert grade_for(45, CONFIG)["label"] == "Weak"
    assert grade_for(10, CONFIG)["label"] == "Critical"


# ── scope exclusion (D1, Task 5) ─────────────────────────────────────────────

def test_out_of_scope_column_is_unscored():
    col = {"name": "batch_id", "data_type": "VARCHAR", "row_count": 100, "distinct_count": 3}
    breakdown = score_column(col_dict=col, assessment_scope="out_of_scope", config=CONFIG)
    assert breakdown["state"] == "unscored"
    assert breakdown["reason"] == "out_of_scope"
    assert "components" not in breakdown


def test_empty_table_column_is_unscored():
    col = {"name": "x", "data_type": "VARCHAR", "row_count": 0, "distinct_count": 0}
    breakdown = score_column(col_dict=col, config=CONFIG)
    assert breakdown["state"] == "unscored"
    assert breakdown["reason"] == "empty"


# ── F4 conflict routing (Task 7) ─────────────────────────────────────────────

def test_conflict_finding_routes_to_validity_no_double_count():
    """A validity/rule finding attaches to Validity (present) — overlay stays full."""
    col = {
        "name": "cur", "data_type": "VARCHAR", "row_count": 1000, "null_count": 0,
        "distinct_count": 5, "uniqueness_pct": 0.005, "invalid_format_count": 0,
    }
    finding = {"severity": "attention", "category": "validity", "provenance": "rule",
               "rationale": "semantic type/value conflict"}
    breakdown = score_column(col_dict=col, findings=[finding], config=CONFIG)
    profile = _component(breakdown, "profile")
    validity = _line_item(profile, "Validity")
    overlay = _line_item(profile, "Findings overlay")
    assert any(f.get("rationale") == "semantic type/value conflict" for f in validity["findings"])
    assert overlay["earned"] == overlay["max"]  # not double-counted in overlay


def test_conflict_finding_falls_to_overlay_when_no_validity_dimension():
    """free_text has no Validity dimension → the finding deducts in the overlay."""
    col = {
        "name": "notes", "data_type": "VARCHAR", "row_count": 1000, "null_count": 0,
        "distinct_count": 900, "uniqueness_pct": 0.9,
    }
    finding = {"severity": "attention", "category": "validity", "provenance": "rule"}
    breakdown = score_column(col_dict=col, findings=[finding], config=CONFIG)
    assert breakdown["archetype"] == "free_text"
    profile = _component(breakdown, "profile")
    overlay = _line_item(profile, "Findings overlay")
    assert overlay["earned"] < overlay["max"]  # attention (2) deducted


def test_ai_finding_always_lands_in_overlay_discounted():
    col = {"name": "cur", "data_type": "VARCHAR", "row_count": 1000, "null_count": 0,
           "distinct_count": 5, "uniqueness_pct": 0.005}
    finding = {"severity": "high", "category": "validity", "provenance": "ai"}
    breakdown = score_column(col_dict=col, findings=[finding], config=CONFIG)
    profile = _component(breakdown, "profile")
    overlay = _line_item(profile, "Findings overlay")
    # high(4) × ai(0.5) = 2 deducted from the 8-point overlay
    assert overlay["earned"] == 6.0


# ── Polish Batch Task 1 — Findings-overlay names what it checks ──────────────

def test_findings_overlay_note_names_the_checks_considered():
    """The overlay's evidence_note carries a one-line hint of what it checks —
    descriptive only, no score impact either way (clean or with findings)."""
    col = {"name": "cur", "data_type": "VARCHAR", "row_count": 1000, "null_count": 0,
           "distinct_count": 5, "uniqueness_pct": 0.005}
    clean = score_column(col_dict=col, config=CONFIG)
    overlay_clean = _line_item(_component(clean, "profile"), "Findings overlay")
    assert "regulatory" in overlay_clean["evidence_note"].lower()
    assert "ai-detected" in overlay_clean["evidence_note"].lower()

    finding = {"severity": "attention", "category": "validity", "provenance": "ai"}
    with_finding = score_column(col_dict=col, findings=[finding], config=CONFIG)
    overlay_with = _line_item(_component(with_finding, "profile"), "Findings overlay")
    assert "regulatory" in overlay_with["evidence_note"].lower()
    # The hint doesn't change the score.
    assert overlay_clean["earned"] == overlay_clean["max"]


# ── validator-backed Validity yardstick (F2 / §10.2) ─────────────────────────

def test_validator_pass_rate_drives_validity_for_accepted_type():
    col = {
        "name": "iban", "data_type": "VARCHAR", "row_count": 1000, "null_count": 0,
        "distinct_count": 900, "uniqueness_pct": 0.9, "inferred_pattern": "IBAN",
        "pattern_confidence": 0.99, "validator_pass_rates": {"iban": 0.90},
    }
    record = {"accepted_at": "2026-08-20T00:00:00Z", "type_id": "iban"}
    breakdown = score_column(col_dict=col, semantic_record=record, config=CONFIG)
    assert breakdown["archetype"] == "text"
    validity = _line_item(_component(breakdown, "profile"), "Validity")
    # invalid_rate = 1 - 0.90 = 0.10; zero_at 0.10 → earned 0
    assert validity["evidence"].get("yardstick") == "validator"
    assert validity["earned"] == 0.0


# ── U2d — plain-language evidence_note per line-item (descriptive only) ───────

def test_every_line_item_carries_an_evidence_note():
    """Worked example A: every scored line-item gets a non-empty note."""
    col = {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }
    breakdown = score_column(
        col_dict=col,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )
    for comp in breakdown["components"]:
        for li in comp["line_items"]:
            assert li.get("evidence_note"), f"{comp['name']}/{li['label']} missing evidence_note"
            # The note explains the formula, it does not replace it.
            assert li.get("formula")


def test_evidence_note_content_names_stat_tolerance_and_outcome():
    col = {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }
    breakdown = score_column(
        col_dict=col,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )
    profile = _component(breakdown, "profile")
    completeness = _line_item(profile, "Completeness")
    assert "tolerance" in completeness["evidence_note"]
    assert "14.0/16" in completeness["evidence_note"]

    validity = _line_item(profile, "Validity")
    assert "fail" in validity["evidence_note"]
    assert "11.2/14" in validity["evidence_note"]

    refdata = _component(breakdown, "reference_data")
    codes = _line_item(refdata, "Codes documented")
    assert "18 of 24 codes documented" in codes["evidence_note"]


def test_full_marks_line_item_note_reads_full():
    """A numeric column with clean validity → Validity note says 'full'."""
    col = {
        "name": "exposure_amount", "data_type": "DECIMAL",
        "row_count": 10000, "null_count": 50, "distinct_count": 8000, "uniqueness_pct": 0.8,
        "empty_string_count": 0, "placeholder_count": 0, "type_mismatch_count": 0,
        "invalid_format_count": None, "suspicious_date_count": 0, "future_date_count": 0,
        "numeric_stddev": 84210.0, "numeric_avg": 152300.0, "numeric_median": 141800.0,
        "numeric_outlier_count": 40, "outlier_detection": "two_sided",
        "top_values": [{"value": "1000", "count": 300}], "constant_run_warning": False,
    }
    breakdown = score_column(
        col_dict=col,
        definition={"present": True, "is_ai": True, "lifecycle": "defined"},
        business_name={"value": "exposure_amount", "source": "ai_or_auto"},
        glossary={"linked": False},
        config=CONFIG,
    )
    validity = _line_item(_component(breakdown, "profile"), "Validity")
    assert "full 10.0/10" in validity["evidence_note"]

    # AI-drafted business name → note primes the remediation path.
    definition = _component(breakdown, "interpretation")
    bn = _line_item(definition, "Business Name")
    assert "remaining" in bn["evidence_note"]
    gl = _line_item(definition, "Glossary Linkage")
    assert "not linked" in gl["evidence_note"]


def test_evidence_note_does_not_change_worked_example_scores():
    """Adding notes must not move any worked-example number (74 / 70)."""
    col_a = {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }
    a = score_column(
        col_dict=col_a,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )
    assert a["dq_score"] == 74

