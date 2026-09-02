"""Tests for core.dq_config — DQScoringConfig loader and load-time invariants."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.dq_config import DQConfigError, DQScoringConfig

_VALID = {
    "model_version": "dq-1",
    "component_weights": {"profile": 50, "interpretation": 30, "reference_data": 20},
    "component_applicability": {"profile": "always", "interpretation": "always", "reference_data": "is_coded"},
    "archetype_detection": {"key_uniqueness_min": 0.995},
    "column_intent_defaults": {"nullability": "unspecified"},
    "profile_dimensions": {
        "key_like": {"completeness": 12, "validity": 10, "uniqueness": 16, "consistency": 4, "findings": 8},
        "numeric": {"completeness": 14, "validity": 10, "consistency": 18, "findings": 8},
    },
    "tolerances": {"validity_zero_at": 0.10},
    "consistency_deductions": {"single_constant": 8},
    "finding_routing": {"dimension_category_map": {"completeness": "completeness"}},
    "persistence": {"trigger": "on_write"},
    "definition_scales": {
        "description": {"present": 3, "authorship_human": 3, "authorship_ai": 1,
                        "lifecycle": {"approved": 5, "defined": 2, "draft": 1}},
        "business_name": {"human": 5, "ai_or_auto": 2, "none": 0},
        "glossary": {"linked": 3, "term_status": {"published": 4, "approved": 3, "confirmed": 2, "draft": 1}},
    },
    "reference_data_scales": {
        "codes_documented_max": 12,
        "status": {"approved": 8, "under_review": 5, "candidate": 2, "none": 0},
    },
    "semantic_line_item": {
        "max": 7,
        "scale": {"confirmed": 1.0, "proposed": 0.5, "suggested": 0.2, "unresolved": 0.0, "rejected": 0.0},
        "type_value_conflict_deduction": 0.3,
    },
    "dataset_scoring": {"component_weights": {"column_rollup": 85, "dataset_integrity": 15}},
    "grade_bands": [
        {"min": 90, "label": "Excellent"},
        {"min": 75, "label": "Good"},
        {"min": 60, "label": "Adequate"},
        {"min": 40, "label": "Weak"},
        {"min": 0, "label": "Critical"},
    ],
}


def _write(tmp_path: Path, overrides: dict | None = None) -> Path:
    data = dict(_VALID)
    data.update(overrides or {})
    path = tmp_path / "dq_scoring_config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_real_repo_config_loads_and_validates():
    config = DQScoringConfig.from_project()
    assert config.model_version == "dq-1"
    assert config.component_weights["profile"] == 50
    assert config.grade_bands[0]["min"] == 90


def test_valid_fixture_loads(tmp_path):
    path = _write(tmp_path)
    config = DQScoringConfig.from_project(path=path)
    assert config.component_weights["profile"] == 50


def test_missing_file_raises(tmp_path):
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=tmp_path / "does_not_exist.yaml")


def test_zero_component_weight_raises(tmp_path):
    path = _write(tmp_path, {"component_weights": {"profile": 0, "interpretation": 30, "reference_data": 20}})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_negative_component_weight_raises(tmp_path):
    path = _write(tmp_path, {"component_weights": {"profile": 50, "interpretation": -1, "reference_data": 20}})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_profile_dimensions_row_not_summing_to_profile_weight_raises(tmp_path):
    path = _write(tmp_path, {
        "profile_dimensions": {
            "key_like": {"completeness": 12, "validity": 10, "uniqueness": 16, "consistency": 4, "findings": 999},
        },
    })
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_grade_bands_missing_zero_floor_raises(tmp_path):
    path = _write(tmp_path, {
        "grade_bands": [{"min": 90, "label": "Excellent"}, {"min": 40, "label": "Weak"}],
    })
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_grade_bands_duplicate_overlap_raises(tmp_path):
    path = _write(tmp_path, {
        "grade_bands": [{"min": 90, "label": "Excellent"}, {"min": 90, "label": "Good"}, {"min": 0, "label": "Critical"}],
    })
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_grade_bands_empty_raises(tmp_path):
    path = _write(tmp_path, {"grade_bands": []})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


# ── SD-R3c: universal line-item ↔ weight closure invariant ────────────────────

def test_component_weights_not_summing_to_100_raises(tmp_path):
    # 50 + 25 + 20 = 95 ≠ 100.
    path = _write(tmp_path, {"component_weights": {"profile": 50, "interpretation": 25, "reference_data": 20}})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_interpretation_line_items_not_summing_to_weight_raises(tmp_path):
    # Semantic Type max 10 → Definition 11 + Business Name 5 + Glossary 7 + Semantic
    # Type 10 = 33 ≠ interpretation weight 30.
    path = _write(tmp_path, {"semantic_line_item": {"max": 10, "scale": {"confirmed": 1.0, "unresolved": 0.0}}})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_reference_data_line_items_not_summing_to_weight_raises(tmp_path):
    # status max 20 → Codes 12 + Approved 20 = 32 ≠ reference_data weight 20.
    path = _write(tmp_path, {"reference_data_scales": {"codes_documented_max": 12, "status": {"approved": 20}}})
    with pytest.raises(DQConfigError):
        DQScoringConfig.from_project(path=path)


def test_semantic_line_item_accessors(tmp_path):
    path = _write(tmp_path)
    config = DQScoringConfig.from_project(path=path)
    assert config.semantic_line_item_max == 7
    assert config.semantic_line_item_scale["confirmed"] == 1.0
    assert config.semantic_type_conflict_deduction == 0.3


def test_real_repo_config_interpretation_line_items_sum_to_weight():
    """The shipped config's Interpretation line-items sum natively to 30."""
    config = DQScoringConfig.from_project()
    interp = config._interpretation_line_item_maxes()
    assert sum(interp.values()) == config.component_weights["interpretation"] == 30
    refdata = config._reference_data_line_item_maxes()
    assert sum(refdata.values()) == config.component_weights["reference_data"] == 20
