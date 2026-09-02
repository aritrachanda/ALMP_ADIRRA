"""Tests for core.dq_remediation — the U4b remediation action slab (DQ §17).

Actions are DERIVED from the line-item gaps the scorer already produced
(``max − earned``, scaled by the reallocation factor) — never invented, never a
re-score. The two worked examples (A: coded → 81, B: numeric/reallocation → 73)
are reused to prove the actions and the path-to-next-grade line up with the
documented breakdown, and that the composite scores are untouched.
"""
from __future__ import annotations

from core.dq_config import DQScoringConfig
from core.dq_remediation import (
    derive_actions,
    inapplicable_components,
    path_to_next_grade,
)
from core.dq_scorer import score_column

# The shipped config IS the 3-component fold (SD-R3c): Profile 50 / Interpretation
# 30 / Reference Data 20, Semantic Type a line-item inside Interpretation. The
# worked examples pass an ACCEPTED semantic record so the Semantic Type line-item
# is full (7/7) and the slab focuses on the other line-items' gaps.
CONFIG = DQScoringConfig.from_project()
_CONFIRMED = {"accepted_at": "2026-08-20T00:00:00Z", "type_id": "country_code", "tier": 1,
              "source": "rule", "type_value_conflict": False}


def _worked_example_a() -> dict:
    col = {
        "name": "counterparty_country", "data_type": "VARCHAR",
        "row_count": 10000, "null_count": 300, "distinct_count": 24,
        "uniqueness_pct": 0.0024, "empty_string_count": 0, "placeholder_count": 12,
        "invalid_format_count": 200, "type_mismatch_count": 0, "suspicious_date_count": 0,
        "future_date_count": 0, "inferred_pattern": "ISO_COUNTRY", "pattern_confidence": 0.97,
        "constant_run_warning": True, "numeric_stddev": None,
        "top_values": [{"value": "FI", "count": 200}],
    }
    return score_column(
        col_dict=col,
        semantic_record=_CONFIRMED,
        definition={"present": True, "is_ai": False, "lifecycle": "approved"},
        business_name={"value": "Counterparty Country", "source": "human"},
        glossary={"linked": True, "term_status": "confirmed"},
        reference_data={"codes_documented": 18, "distinct_count": 24, "status": "under_review"},
        config=CONFIG,
    )


def _worked_example_b() -> dict:
    col = {
        "name": "exposure_amount", "data_type": "DECIMAL",
        "row_count": 10000, "null_count": 50, "distinct_count": 9800,
        "uniqueness_pct": 0.98, "empty_string_count": 0, "placeholder_count": 0,
        "type_mismatch_count": 0, "numeric_outlier_count": 40, "numeric_stddev": 84210,
        "numeric_avg": 152300, "numeric_median": 141800,
        "top_values": [{"value": "1000", "count": 300}],
    }
    return score_column(
        col_dict=col,
        semantic_record={"accepted_at": "2026-08-20T00:00:00Z", "type_id": "monetary_amount",
                         "tier": 1, "source": "rule", "type_value_conflict": False},
        definition={"present": True, "is_ai": True, "lifecycle": "defined"},
        business_name={"value": "exposure_amount", "source": "ai_or_auto"},
        glossary={"linked": False},
        config=CONFIG,
    )


# ── derivation ───────────────────────────────────────────────────────────────

def test_actions_derived_from_example_a_gaps_scores_untouched():
    breakdown = _worked_example_a()
    assert breakdown["dq_score"] == 81  # score NOT changed by the slab

    actions = breakdown["actions"]
    # Every action maps to a real gap; nothing invented.
    assert actions, "expected improvement actions for a non-perfect column"
    # Impact-sorted, largest first (constant-run consistency gap of 6.0 leads).
    assert [a["points"] for a in actions] == sorted((a["points"] for a in actions), reverse=True)
    assert actions[0]["line_item"] == "Consistency"
    assert actions[0]["points"] == 6.0
    assert actions[0]["component"] == "profile"
    # A full line-item (Definition 14/14, Findings 8/8, Business Name 6/6) yields NO action.
    labels = {a["line_item"] for a in actions}
    assert "Definition" not in labels
    assert "Findings overlay" not in labels
    assert "Business Name" not in labels
    # Reference-data gaps present, each carrying an action_type + step.
    codes = next(a for a in actions if a["line_item"] == "Codes documented")
    assert codes["points"] == 3.0
    assert codes["action_type"] == "governance"
    assert codes["step"]


def test_full_line_items_produce_no_action():
    # A synthetic perfect breakdown → zero actions.
    record = {
        "state": "scored", "dq_score": 100, "grade_label": "Excellent",
        "reallocation_factor": 1.0, "applicable_components": ["profile"],
        "components": [
            {"name": "profile", "line_items": [
                {"label": "Completeness", "earned": 16, "max": 16},
                {"label": "Validity", "earned": 14, "max": 14},
            ]},
        ],
    }
    assert derive_actions(record, CONFIG) == []


def test_points_scaled_by_reallocation_factor():
    # Example B reallocates ×1.25 — a glossary gap earns 1.25× its raw points.
    breakdown = _worked_example_b()
    assert breakdown["dq_score"] == 79
    assert breakdown["reallocation_factor"] == 1.25

    actions = breakdown["actions"]
    glossary = next(a for a in actions if a["line_item"] == "Glossary Linkage")
    # Raw gap 7 (unlinked, max 7) → 7 × 1.25 = 8.75 → 8.8 composite points.
    assert glossary["points"] == 8.8
    assert glossary["action_type"] == "governance"
    # Validity is full (10/10) → no action.
    assert "Validity" not in {a["line_item"] for a in actions}


# ── path to next grade ───────────────────────────────────────────────────────

def test_path_to_next_grade_example_a_two_actions_reach_excellent():
    breakdown = _worked_example_a()
    path = breakdown["path_to_next_grade"]
    assert path["at_top_band"] is False
    assert path["current_score"] == 81
    assert path["next_grade"] == "Excellent"
    assert path["next_grade_min"] == 90
    assert path["points_needed"] == 9.0
    # Minimal set: constant-run (+6.0) then codes documented (+3.0) = +9.0.
    assert [a["line_item"] for a in path["actions"]] == ["Consistency", "Codes documented"]
    assert path["reachable"] is True


def test_path_to_next_grade_example_b_reaches_excellent():
    breakdown = _worked_example_b()
    path = breakdown["path_to_next_grade"]
    assert path["current_score"] == 79
    assert path["next_grade"] == "Excellent"
    assert path["points_needed"] == 11.0
    # Glossary (+8.8) then Definition (+6.3) cross the 90 threshold.
    assert [a["line_item"] for a in path["actions"]] == ["Glossary Linkage", "Definition"]
    assert path["reachable"] is True


def test_path_to_next_grade_top_band_needs_no_actions():
    record = {
        "state": "scored", "dq_score": 95, "grade_label": "Excellent",
        "reallocation_factor": 1.0, "applicable_components": ["profile"],
        "components": [],
    }
    path = path_to_next_grade(record, [], CONFIG)
    assert path["at_top_band"] is True
    assert path["next_grade"] is None
    assert path["actions"] == []


def test_unscored_record_has_no_actions_or_path():
    record = {"state": "unscored", "reason": "out_of_scope"}
    assert derive_actions(record, CONFIG) == []
    assert path_to_next_grade(record, [], CONFIG) is None


# ── inapplicable components (legibility #4 feed) ──────────────────────────────

def test_inapplicable_components_names_reference_data_on_numeric():
    breakdown = _worked_example_b()
    assert inapplicable_components(breakdown, CONFIG) == ["reference_data"]


def test_inapplicable_components_empty_when_all_apply():
    breakdown = _worked_example_a()
    assert inapplicable_components(breakdown, CONFIG) == []


# ── U4b-fix — gap-aware, plain-language actions with a destination ────────────

def test_glossary_action_is_gap_aware_not_link_when_already_linked():
    # Example A is linked with a 'confirmed' term (9/10) — the residual is the
    # term status, NOT the link. The action must never say "link" here.
    breakdown = _worked_example_a()
    glossary = next(
        a for a in breakdown["actions"] if a["line_item"] == "Glossary Linkage"
    )
    step = glossary["step"].lower()
    assert "already linked" in step
    assert "published" in step
    # The false "link this column" instruction must be gone.
    assert "link this column to a glossary term" not in step


def test_glossary_action_says_link_only_when_unlinked():
    # Example B is unlinked → the honest step IS to link it.
    breakdown = _worked_example_b()
    glossary = next(
        a for a in breakdown["actions"] if a["line_item"] == "Glossary Linkage"
    )
    assert "link this column to a glossary term" in glossary["step"].lower()


def test_definition_action_gap_aware_ai_drafted():
    # Example B's description is AI-drafted, unreviewed → "review", not "write".
    breakdown = _worked_example_b()
    definition = next(
        a for a in breakdown["actions"] if a["line_item"] == "Definition"
    )
    step = definition["step"].lower()
    assert "ai-drafted" in step or "review" in step
    assert "write a short business-friendly description" not in step


def test_business_name_action_gap_aware_auto_derived():
    # Example B's business name is auto-derived → "confirm", not "give it a name".
    breakdown = _worked_example_b()
    bn = next(a for a in breakdown["actions"] if a["line_item"] == "Business Name")
    assert "auto-generated" in bn["step"].lower() or "confirm" in bn["step"].lower()


def test_code_set_action_gap_aware_advances_from_current_status():
    # Example A's code set is 'under_review' → advance it, not "submit".
    breakdown = _worked_example_a()
    code_set = next(
        a for a in breakdown["actions"] if a["line_item"] == "Code set approved"
    )
    step = code_set["step"].lower()
    assert "under_review" in step
    assert "advance" in step


def test_consistency_action_is_plain_language_no_jargon():
    breakdown = _worked_example_a()
    consistency = next(
        a for a in breakdown["actions"] if a["line_item"] == "Consistency"
    )
    step = consistency["step"].lower()
    # Plain-language rewrite — no raw "plausibility" / "constant run" jargon.
    assert "plausibility" not in step
    assert "look unusual" in step or "far outside" in step


def test_each_action_carries_a_destination_score_and_grade():
    breakdown = _worked_example_a()
    assert breakdown["dq_score"] == 81
    for action in breakdown["actions"]:
        # +points lands the column at dq_score + points, with the grade there.
        assert action["resulting_score"] == round(81 + action["points"], 1)
        assert action["resulting_grade"] in {
            "Excellent", "Good", "Adequate", "Weak", "Critical",
        }


def test_path_reports_real_landing_score_not_band_threshold():
    # Example B: 79, the path (glossary +8.8, definition +6.3) crosses into
    # Excellent. The landing is 79 + 8.8 + 6.3 = 94.1 (real destination), NOT the
    # band threshold 90.
    breakdown = _worked_example_b()
    path = breakdown["path_to_next_grade"]
    assert path["next_grade"] == "Excellent"
    assert path["next_grade_min"] == 90
    assert path["landing_score"] == 94.1
    assert path["landing_grade"] == "Excellent"
    # points_needed (to the threshold) is retained for prioritisation.
    assert path["points_needed"] == 11.0


# ── Polish Batch Task 3 — outlier action names the actual signal ────────────

def test_consistency_action_names_outlier_count_and_range_when_available():
    # Example B carries numeric_outlier_count/avg/stddev — the Consistency gap
    # (from the outlier_penalty deduction) should name the count and the
    # mean ± 3σ range, not the generic "some values look unusual".
    breakdown = _worked_example_b()
    consistency = next(
        (a for a in breakdown["actions"] if a["line_item"] == "Consistency"), None
    )
    assert consistency is not None, "expected a Consistency gap from the outlier deduction"
    step = consistency["step"]
    assert "40" in step  # numeric_outlier_count
    assert "±" in step or "3\u03c3" in step
    assert "plausibility" not in step.lower()


def test_consistency_action_falls_back_when_range_unavailable():
    # Outlier count known, but no mean/stddev captured — say what IS known
    # (the count), never invent a range.
    col = {
        "name": "measure", "data_type": "DECIMAL", "row_count": 1000, "null_count": 0,
        "distinct_count": 500, "uniqueness_pct": 0.5, "numeric_outlier_count": 5,
    }
    breakdown = score_column(col_dict=col, config=CONFIG)
    consistency = next(
        (a for a in breakdown["actions"] if a["line_item"] == "Consistency"), None
    )
    assert consistency is not None
    step = consistency["step"]
    assert "5" in step
    assert "≈" not in step  # no invented numeric range


# ── Polish Batch Task 4 — tied-impact path wording ───────────────────────────

def test_path_flags_any_one_suffices_when_pivotal_action_has_a_tie():
    record = {
        "state": "scored", "dq_score": 60, "grade_label": "Adequate",
        "reallocation_factor": 1.0,
    }
    actions = [
        {"component": "definition", "line_item": "Business Name", "points": 17.5,
         "step": "x", "action_type": "governance"},
        {"component": "definition", "line_item": "Glossary Linkage", "points": 17.5,
         "step": "y", "action_type": "governance"},
        {"component": "profile", "line_item": "Completeness", "points": 5.0,
         "step": "z", "action_type": "data"},
    ]
    path = path_to_next_grade(record, actions, CONFIG)
    assert path["next_grade"] == "Good"
    assert path["points_needed"] == 15.0
    assert path["any_one_suffices"] is True
    assert {a["line_item"] for a in path["actions"]} == {"Business Name", "Glossary Linkage"}
    # The score math is untouched — landing is still +17.5 (one action), not +35.
    assert path["landing_score"] == 77.5


def test_path_any_one_suffices_false_when_multiple_actions_genuinely_required():
    # Example A needs two DIFFERENT-impact actions (6.0 + 3.0) — no tie, no flag.
    breakdown = _worked_example_a()
    path = breakdown["path_to_next_grade"]
    assert path["any_one_suffices"] is False


def test_path_any_one_suffices_false_at_top_band():
    record = {
        "state": "scored", "dq_score": 95, "grade_label": "Excellent",
        "reallocation_factor": 1.0, "applicable_components": ["profile"],
        "components": [],
    }
    path = path_to_next_grade(record, [], CONFIG)
    assert path["any_one_suffices"] is False


def test_path_landing_for_example_a():
    # Example A: 81, two actions (+6.0, +3.0) reach exactly 90 → Excellent.
    breakdown = _worked_example_a()
    path = breakdown["path_to_next_grade"]
    assert path["landing_score"] == 90.0
    assert path["landing_grade"] == "Excellent"


def test_top_band_path_landing_is_current_score():
    record = {
        "state": "scored", "dq_score": 95, "grade_label": "Excellent",
        "reallocation_factor": 1.0, "applicable_components": ["profile"],
        "components": [],
    }
    path = path_to_next_grade(record, [], CONFIG)
    assert path["at_top_band"] is True
    assert path["landing_score"] == 95
    assert path["landing_grade"] == "Excellent"
