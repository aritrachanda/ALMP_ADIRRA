"""Tests for core.assessment.profile_fingerprint — U0 Task 7 (outlier_detection marker)."""
from __future__ import annotations

from core.assessment import profile_fingerprint


def _profile(outlier_detection=None, numeric_outlier_count=0):
    return {
        "schema_name": "src",
        "table_name": "accounts",
        "row_count": 10,
        "columns": [
            {
                "name": "amount",
                "data_type": "DOUBLE",
                "null_pct": 0.0,
                "distinct_count": 10,
                "numeric_outlier_count": numeric_outlier_count,
                "outlier_detection": outlier_detection,
            }
        ],
    }


def test_fingerprint_changes_when_outlier_detection_marker_changes():
    before = profile_fingerprint(_profile(outlier_detection=None, numeric_outlier_count=0))
    after = profile_fingerprint(_profile(outlier_detection="two_sided", numeric_outlier_count=1))
    assert before != after


def test_fingerprint_stable_when_nothing_changes():
    a = profile_fingerprint(_profile(outlier_detection="two_sided", numeric_outlier_count=1))
    b = profile_fingerprint(_profile(outlier_detection="two_sided", numeric_outlier_count=1))
    assert a == b


def test_fingerprint_unaffected_by_code_values_or_decimal_scale_distribution():
    """code_values / decimal_scale_distribution must NOT be fingerprinted (U0 scope)."""
    profile = _profile()
    profile["columns"][0]["code_values"] = [{"value": "A", "count": 1}]
    profile["columns"][0]["decimal_scale_distribution"] = {2: 1.0}
    with_extras = profile_fingerprint(profile)

    bare = profile_fingerprint(_profile())
    assert with_extras == bare
