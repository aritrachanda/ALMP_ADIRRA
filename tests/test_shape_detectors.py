"""Tests for core.shape_detectors — the shared numeric-shape signal library."""
from __future__ import annotations

from core.shape_detectors import (
    bounded_range,
    currency_sibling,
    decimal_scale_consistent,
    declared_scale,
    low_cardinality_enum,
    sign_distribution,
    unique_ratio,
    year_like_range,
)


# ── decimal_scale_consistent ────────────────────────────────────────────────

def test_decimal_scale_consistent_fires_from_values():
    result = decimal_scale_consistent(["1.25", "2.50", "3.75", "4.00"], {})
    assert result["fired"] is True
    assert result["share"] == 1.0


def test_decimal_scale_consistent_not_fired_mixed_scales():
    result = decimal_scale_consistent(["1.2", "2.567", "3", "4.891"], {}, min_share=0.9)
    assert result["fired"] is False


def test_decimal_scale_consistent_prefers_profiler_distribution():
    result = decimal_scale_consistent([], {"decimal_scale_distribution": {2: 0.97, 0: 0.03}})
    assert result["fired"] is True
    assert result["detail"].startswith("97.0%")


def test_decimal_scale_consistent_empty_values():
    result = decimal_scale_consistent([], {})
    assert result["fired"] is False
    assert result["share"] is None


def test_decimal_scale_consistent_all_null():
    result = decimal_scale_consistent([None, None], {})
    assert result["fired"] is False


# ── declared_scale ───────────────────────────────────────────────────────────

def test_declared_scale_fires():
    result = declared_scale({"declared_scale": 2})
    assert result["fired"] is True


def test_declared_scale_not_fired_below_min():
    result = declared_scale({"declared_scale": 0}, min_scale=2)
    assert result["fired"] is False


def test_declared_scale_absent():
    result = declared_scale({})
    assert result["fired"] is False
    assert result["share"] is None


# ── bounded_range ────────────────────────────────────────────────────────────

def test_bounded_range_fires_for_percentages():
    result = bounded_range([10, 20, 55.5, 99.9], {})
    assert result["fired"] is True


def test_bounded_range_not_fired_out_of_range():
    result = bounded_range([1000, 2000, -500], {})
    assert result["fired"] is False


def test_bounded_range_single_value():
    result = bounded_range([0.5], {})
    assert result["fired"] is True
    assert result["share"] == 1.0


def test_bounded_range_empty_falls_back_to_profiler_minmax():
    result = bounded_range([], {"min_value": "0", "max_value": "100"})
    assert result["fired"] is True


def test_bounded_range_empty_no_profiler_stats():
    result = bounded_range([], {})
    assert result["fired"] is False
    assert result["share"] is None


# ── sign_distribution ────────────────────────────────────────────────────────

def test_sign_distribution_reports_shares():
    result = sign_distribution([100.0, 250.5, -10.0, 0])
    assert result["fired"] is True
    assert "positive=" in result["detail"]
    assert "negative=" in result["detail"]


def test_sign_distribution_negative_amounts():
    result = sign_distribution([-5, -10, -15])
    assert result["fired"] is True
    assert result["share"] == 1.0


def test_sign_distribution_empty_values():
    result = sign_distribution([])
    assert result["fired"] is False
    assert result["share"] is None


def test_sign_distribution_all_null():
    result = sign_distribution([None, None])
    assert result["fired"] is False


# ── year_like_range ──────────────────────────────────────────────────────────

def test_year_like_range_fires():
    result = year_like_range([1999, 2005, 2024, 2000])
    assert result["fired"] is True


def test_year_like_range_not_fired_random_numbers():
    result = year_like_range([5, 10, 42, 7])
    assert result["fired"] is False


def test_year_like_range_single_value():
    result = year_like_range([2020])
    assert result["fired"] is True
    assert result["share"] == 1.0


def test_year_like_range_empty_values():
    result = year_like_range([])
    assert result["fired"] is False
    assert result["share"] is None


# ── unique_ratio ─────────────────────────────────────────────────────────────

def test_unique_ratio_fires_from_uniqueness_pct():
    result = unique_ratio({"uniqueness_pct": 0.995})
    assert result["fired"] is True


def test_unique_ratio_not_fired_low_uniqueness():
    result = unique_ratio({"uniqueness_pct": 0.10})
    assert result["fired"] is False


def test_unique_ratio_falls_back_to_distinct_and_row_count():
    result = unique_ratio({"distinct_count": 995, "row_count": 1000})
    assert result["fired"] is True


def test_unique_ratio_no_data():
    result = unique_ratio({})
    assert result["fired"] is False
    assert result["share"] is None


# ── low_cardinality_enum ─────────────────────────────────────────────────────

def test_low_cardinality_enum_fires_small_distinct():
    result = low_cardinality_enum({"distinct_count": 3, "row_count": 10000})
    assert result["fired"] is True


def test_low_cardinality_enum_not_fired_high_cardinality():
    result = low_cardinality_enum({"distinct_count": 5000, "row_count": 10000})
    assert result["fired"] is False


def test_low_cardinality_enum_no_distinct_count():
    result = low_cardinality_enum({})
    assert result["fired"] is False
    assert result["share"] is None


# ── currency_sibling ─────────────────────────────────────────────────────────

def test_currency_sibling_detects_name_token():
    table = {"columns": [{"name": "amount"}, {"name": "currency_code"}]}
    assert currency_sibling(table) is True


def test_currency_sibling_detects_inferred_pattern():
    table = {"columns": [{"name": "amount"}, {"name": "ccy_col", "inferred_pattern": "CURRENCY"}]}
    assert currency_sibling(table) is True


def test_currency_sibling_false_when_no_match():
    table = {"columns": [{"name": "amount"}, {"name": "balance"}]}
    assert currency_sibling(table) is False


def test_currency_sibling_empty_table():
    assert currency_sibling({}) is False
    assert currency_sibling(None) is False
