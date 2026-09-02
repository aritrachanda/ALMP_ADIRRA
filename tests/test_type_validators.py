"""Tests for core.type_validators — focused on the new timestamp_parse validator (U0 Task 2)."""
from __future__ import annotations

from core.type_validators import known_validators, run_validator, run_validator_detail, timestamp_parse


def test_timestamp_parse_iso8601_with_timezone():
    assert timestamp_parse(["2024-05-01T10:30:00+02:00", "2024-05-02T10:30:00Z"]) == 1.0


def test_timestamp_parse_iso8601_without_timezone():
    assert timestamp_parse(["2024-05-01T10:30:00", "2024-05-02T10:30:00.123456"]) == 1.0


def test_timestamp_parse_plain_space_separated():
    assert timestamp_parse(["2024-05-01 10:30:00", "2024-05-02 10:30:00.500"]) == 1.0


def test_timestamp_parse_epoch_seconds():
    # 2024-01-01T00:00:00Z ~ 1704067200
    assert timestamp_parse(["1704067200"]) == 1.0


def test_timestamp_parse_epoch_millis():
    # 2024-01-01T00:00:00Z in millis
    assert timestamp_parse(["1704067200000"]) == 1.0


def test_timestamp_parse_out_of_range_year_fails():
    assert timestamp_parse(["1899-12-31T00:00:00"]) == 0.0
    assert timestamp_parse(["2101-01-01T00:00:00"]) == 0.0


def test_timestamp_parse_garbage_fails():
    assert timestamp_parse(["not-a-timestamp", "12345"]) == 0.0


def test_timestamp_parse_mixed_samples_partial_rate():
    rate = timestamp_parse(["2024-05-01T10:30:00", "garbage"])
    assert rate == 0.5


def test_timestamp_parse_blank_and_none_ignored():
    assert timestamp_parse([None, "", "  ", "2024-05-01T10:30:00"]) == 1.0


def test_timestamp_parse_empty_iterable():
    assert timestamp_parse([]) == 0.0


def test_timestamp_parse_registered_in_known_validators():
    assert "timestamp_parse" in known_validators()


def test_run_validator_dispatches_timestamp_parse():
    assert run_validator("timestamp_parse", ["2024-05-01T10:30:00"]) == 1.0


def test_run_validator_detail_dispatches_timestamp_parse():
    rate, passing, failing = run_validator_detail("timestamp_parse", ["2024-05-01T10:30:00", "garbage"])
    assert rate == 0.5
    assert passing == ["2024-05-01T10:30:00"]
    assert failing == ["garbage"]


# ── BIC structure (ISO 9362) + ISO 3166 country-code check ────────────────────
from core.type_validators import bic_structure  # noqa: E402


def test_bic_accepts_real_bics_8_and_11_char():
    # Deutsche Bank (8), Nordea Finland (8), JPMorgan London (8), with-branch (11).
    assert bic_structure(["DEUTDEFF", "NDEAFIHH", "CHASGB2L", "DEUTDEFF500"]) == 1.0


def test_bic_rejects_shape_lookalike_with_invalid_country():
    # 'Application' is 11 letters and matches a shape-only regex, but characters
    # 5-6 ('IC') are not a real ISO 3166 country, so it must fail.
    assert bic_structure(["Application"]) == 0.0
    assert bic_structure(["ABCDIC2A"]) == 0.0


def test_bic_rejects_reserved_test_and_passive_location_marker():
    # Second character of the location code may not be '0' (test) or '1' (passive).
    assert bic_structure(["DEUTDEF0"]) == 0.0
    assert bic_structure(["DEUTDEF1"]) == 0.0


def test_bic_is_case_insensitive_for_real_values():
    assert bic_structure(["deutdeff"]) == 1.0
