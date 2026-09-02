"""Tests for core.extractors.profiler._enrich_column additions (U0 Task 6).

Covers: full code list (Task 6.1), two-sided outliers (Task 6.2), and the
decimal-scale distribution (Task 6.3). All three fields are additive and
optional — absence degrades gracefully, verified below.
"""
from __future__ import annotations

import core.extractors.profiler as profiler
from core.connectors import DuckDBConnector


def _connector() -> DuckDBConnector:
    conn = DuckDBConnector({"name": "test", "type": "duckdb", "database": ":memory:"})
    conn.connect()
    return conn


# ── Task 6.1 — full code list ───────────────────────────────────────────────

def test_code_values_full_list_for_low_cardinality_column():
    conn = _connector()
    conn.execute("CREATE TABLE t (status VARCHAR)")
    conn.execute("INSERT INTO t VALUES ('A'), ('A'), ('B'), ('C'), ('C'), ('C')")
    profile = profiler._enrich_column(conn, "t", {"name": "status", "data_type": "VARCHAR"}, 6)

    assert profile["distinct_count"] == 3
    assert profile["code_values"] is not None
    values = {row["value"]: row["count"] for row in profile["code_values"]}
    assert values == {"A": 2, "B": 1, "C": 3}


def test_code_values_absent_above_distinct_threshold():
    conn = _connector()
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.execute("INSERT INTO t SELECT * FROM range(0, 60)")
    profile = profiler._enrich_column(conn, "t", {"name": "v", "data_type": "INTEGER"}, 60)

    assert profile["distinct_count"] == 60
    assert profile["code_values"] is None


def test_sample_values_unaffected_by_code_values_addition():
    conn = _connector()
    conn.execute("CREATE TABLE t (status VARCHAR)")
    conn.execute("INSERT INTO t VALUES ('A'), ('B')")
    profile = profiler._enrich_column(conn, "t", {"name": "status", "data_type": "VARCHAR"}, 2)

    assert isinstance(profile["sample_values"], list)
    assert set(profile["sample_values"]) == {"A", "B"}


# ── Task 6.2 — two-sided outliers ───────────────────────────────────────────

def test_two_sided_outliers_catches_negative_direction():
    conn = _connector()
    conn.execute("CREATE TABLE t (amount DOUBLE)")
    values = [1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 1.02, 0.98, 1.0]
    values_sql = ", ".join(f"({v})" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    conn.execute("INSERT INTO t VALUES (-500.0)")
    profile = profiler._enrich_column(conn, "t", {"name": "amount", "data_type": "DOUBLE"}, 11)

    assert profile["outlier_detection"] == "two_sided"
    assert profile["numeric_outlier_count"] == 1


def test_two_sided_outliers_still_catches_positive_direction():
    conn = _connector()
    conn.execute("CREATE TABLE t (amount DOUBLE)")
    values = [1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 1.02, 0.98, 1.0]
    values_sql = ", ".join(f"({v})" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    conn.execute("INSERT INTO t VALUES (500.0)")
    profile = profiler._enrich_column(conn, "t", {"name": "amount", "data_type": "DOUBLE"}, 11)

    assert profile["outlier_detection"] == "two_sided"
    assert profile["numeric_outlier_count"] == 1


def test_outlier_fields_absent_for_non_numeric_column():
    conn = _connector()
    conn.execute("CREATE TABLE t (name VARCHAR)")
    conn.execute("INSERT INTO t VALUES ('alice'), ('bob')")
    profile = profiler._enrich_column(conn, "t", {"name": "name", "data_type": "VARCHAR"}, 2)

    assert profile["numeric_outlier_count"] is None
    assert profile["outlier_detection"] is None


# ── Task 6.3 — decimal-scale distribution ───────────────────────────────────

def test_decimal_scale_distribution_persisted():
    conn = _connector()
    conn.execute("CREATE TABLE t (rate DOUBLE)")
    conn.execute("INSERT INTO t VALUES (1.25), (2.50), (3.75), (4.10)")
    profile = profiler._enrich_column(conn, "t", {"name": "rate", "data_type": "DOUBLE"}, 4)

    assert profile["decimal_scale_distribution"] is not None
    assert abs(sum(profile["decimal_scale_distribution"].values()) - 1.0) < 1e-9


def test_decimal_scale_distribution_none_for_non_numeric_column():
    conn = _connector()
    conn.execute("CREATE TABLE t (name VARCHAR)")
    conn.execute("INSERT INTO t VALUES ('alice'), ('bob')")
    profile = profiler._enrich_column(conn, "t", {"name": "name", "data_type": "VARCHAR"}, 2)

    assert profile["decimal_scale_distribution"] is None


def test_decimal_scale_distribution_none_for_all_null_column():
    conn = _connector()
    conn.execute("CREATE TABLE t (rate DOUBLE)")
    conn.execute("INSERT INTO t VALUES (NULL), (NULL)")
    profile = profiler._enrich_column(conn, "t", {"name": "rate", "data_type": "DOUBLE"}, 2)

    assert profile["decimal_scale_distribution"] is None


# ── Business ID (Y-Tunnus) vs personal ID (Henkilotunnus) pattern split ─────
# A business ID is a company's identifier, not personal data — it must be tagged
# its own pattern name, distinct from PII, so it is never eligible for a PII badge.

def test_y_tunnus_column_tagged_business_id_not_pii():
    conn = _connector()
    conn.execute("CREATE TABLE t (bank_business_id VARCHAR)")
    values = [f"{1000000 + i}-{i % 10}" for i in range(30)]
    values_sql = ", ".join(f"('{v}')" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    profile = profiler._enrich_column(conn, "t", {"name": "bank_business_id", "data_type": "VARCHAR"}, len(values))

    assert profile["inferred_pattern"] == "BUSINESS_ID"


def test_henkilotunnus_column_still_tagged_pii():
    conn = _connector()
    conn.execute("CREATE TABLE t (national_id VARCHAR)")
    check_chars = "0123456789ABCDEFGHJKLMNPRSTUVWXY"
    values = [f"01019{i % 10}-123{check_chars[i % len(check_chars)]}" for i in range(30)]
    values_sql = ", ".join(f"('{v}')" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    profile = profiler._enrich_column(conn, "t", {"name": "national_id", "data_type": "VARCHAR"}, len(values))

    assert profile["inferred_pattern"] == "PII"


def test_henkilotunnus_2000s_century_signs_tagged_pii():
    """2023 DVV expansion: A/B/C/D/E/F are valid 2000s century signs, not just '-'."""
    conn = _connector()
    conn.execute("CREATE TABLE t (national_id VARCHAR)")
    check_chars = "0123456789ABCDEFGHJKLMNPRSTUVWXY"
    signs = "ABCDEF"
    values = [f"01011{i % 10}{signs[i % len(signs)]}123{check_chars[i % len(check_chars)]}" for i in range(30)]
    values_sql = ", ".join(f"('{v}')" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    profile = profiler._enrich_column(conn, "t", {"name": "national_id", "data_type": "VARCHAR"}, len(values))

    assert profile["inferred_pattern"] == "PII"


def test_henkilotunnus_1900s_expanded_century_signs_tagged_pii():
    """2023 DVV expansion: U/V/W/X/Y are also valid 1900s century signs, not just '-'."""
    conn = _connector()
    conn.execute("CREATE TABLE t (national_id VARCHAR)")
    check_chars = "0123456789ABCDEFGHJKLMNPRSTUVWXY"
    signs = "UVWXY"
    values = [f"01019{i % 10}{signs[i % len(signs)]}123{check_chars[i % len(check_chars)]}" for i in range(30)]
    values_sql = ", ".join(f"('{v}')" for v in values)
    conn.execute(f"INSERT INTO t VALUES {values_sql}")
    profile = profiler._enrich_column(conn, "t", {"name": "national_id", "data_type": "VARCHAR"}, len(values))

    assert profile["inferred_pattern"] == "PII"


# ── BIC detector hardening (Phase 5b.3) ──────────────────────────────────────
# _detect_bic now delegates to core.type_validators._bic_valid, so the profiler's
# inferred BIC pattern uses the ISO 9362 layout (incl. char-8 not-'0'/'1' rule)
# plus an ISO 3166 country check on chars 5-6, instead of the old 8/11-alnum shape.

def test_detect_bic_accepts_real_bics():
    assert profiler._detect_bic("DEUTDEFF") is True
    assert profiler._detect_bic("DEUTDEFF500") is True
    assert profiler._detect_bic("NDEAFIHH") is True


def test_detect_bic_is_case_insensitive():
    assert profiler._detect_bic("deutdeff") is True


def test_detect_bic_rejects_shape_lookalike_with_invalid_country():
    # 8 alphanumeric chars but 'IC' (chars 5-6) is not an ISO 3166 country —
    # the old shape-only check accepted these; the hardened one rejects them.
    assert profiler._detect_bic("Applicat") is False
    assert profiler._detect_bic("ABCDIC2A") is False


def test_detect_bic_rejects_reserved_test_and_passive_location_marker():
    assert profiler._detect_bic("DEUTDEF0") is False
    assert profiler._detect_bic("DEUTDEF1") is False


def test_detect_bic_rejects_empty_and_wrong_length():
    assert profiler._detect_bic("") is False
    assert profiler._detect_bic("DEUT") is False
    assert profiler._detect_bic("DEUTDEFF5") is False

