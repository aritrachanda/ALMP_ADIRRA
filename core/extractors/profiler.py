"""
extractors.profiler  –  Data profiling: column stats, constraints, enrichment.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "core"))

from connectors import load_connector  # noqa: E402
from type_validators import _bic_valid  # noqa: E402
import math
import re


def _sanitize_numbers(obj):
    """Recursively replace non-finite float values (inf, -inf, nan) with None."""
    if isinstance(obj, dict):
        return {k: _sanitize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_numbers(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


# ---------------------------------------------------------------------------
# Pattern validators for text columns (IBAN, LEI, BIC, Phone, Email, URL, PII)
# ---------------------------------------------------------------------------

def _is_text_column(data_type: str) -> bool:
    """Check if column is text-like (VARCHAR, TEXT, etc)."""
    if not data_type:
        return False
    dt = data_type.upper()
    return any(t in dt for t in ['VARCHAR', 'TEXT', 'STRING', 'CHAR', 'CLOB'])


def _detect_iban(value: str) -> bool:
    """IBAN: 2 letters + 2 digits + 1-30 alphanumeric. Simple format check."""
    if not value or len(value) < 15 or len(value) > 34:
        return False
    if not re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]+$', value.upper()):
        return False
    return True


def _detect_lei(value: str) -> bool:
    """LEI: exactly 20 alphanumeric characters."""
    if not value or len(value) != 20:
        return False
    return re.match(r'^[A-Z0-9]{20}$', value.upper()) is not None


def _detect_bic(value: str) -> bool:
    """BIC/SWIFT (ISO 9362).

    Delegates to core.type_validators._bic_valid so the profiler's inferred
    BIC pattern uses the same stricter gates as confirmation: the ISO 9362
    regex (including the char-8 not-'0'/'1' rule) plus an ISO 3166 country
    check on characters 5-6. This rejects shape-only look-alikes such as
    'Application' that the old 8-or-11-alnum check accepted.
    """
    if not value:
        return False
    return _bic_valid(value)


def _detect_phone(value: str) -> bool:
    """Phone: international format +CC... or starts with digit, mostly digits/spaces/dashes."""
    if not value:
        return False
    cleaned = re.sub(r'[\s\-().+]', '', value)
    if not cleaned:
        return False
    return cleaned.isdigit() and len(cleaned) >= 7 and len(cleaned) <= 15


def _detect_email(value: str) -> bool:
    """Email: basic RFC-like pattern."""
    if not value or '@' not in value:
        return False
    pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    return re.match(pattern, value) is not None


def _detect_url(value: str) -> bool:
    """URL: starts with http/https/ftp, contains ://"""
    if not value:
        return False
    return re.match(r'^(https?|ftp)://', value, re.IGNORECASE) is not None


def _detect_pii_ytunnus(value: str) -> bool:
    """Y-Tunnus (Finnish Business ID): NNNNNNN-N format."""
    if not value:
        return False
    return re.match(r'^\d{7}-\d{1}$', value) is not None


def _detect_pii_henkilotunnus(value: str) -> bool:
    """Henkilötunnus (Finnish personal ID): DDMMYY[century-sign]NNNC or DDMMYYYNNNNC format.

    Century sign is + (1800s), one of -/U/V/W/X/Y (1900s — expanded in 2023 by DVV to
    solve individual-number exhaustion), or one of A/B/C/D/E/F (2000s, also 2023)."""
    if not value:
        return False
    # Historical + modern century signs: DDMMYY[+-UVWXYABCDEF]NNNC
    if re.match(r'^\d{6}[+\-UVWXYABCDEF]\d{3}[0-9A-Y]$', value):
        return True
    # Modern format: DDMMYYYNNNNC
    if re.match(r'^\d{12}[0-9A-Y]$', value):
        return True
    return False


def _detect_pattern_in_column(conn, full_table: str, col_name: str, data_type: str, table_row_count: int) -> tuple[str | None, float, int]:
    """Detect pattern in a text column. Returns (pattern_name, confidence, invalid_count).
    
    Patterns checked (in priority order):
    1. PII (Henkilötunnus — a real person's ID) → "PII" with high confidence
    2. BUSINESS_ID (Y-Tunnus — a company's ID, NOT personal data) → "BUSINESS_ID"
    3. IBAN → "IBAN"
    4. LEI → "LEI"
    5. BIC → "BIC"
    6. Email → "EMAIL"
    7. URL → "URL"
    7. Phone → "PHONE"
    8. UUID → "UUID"
    9. DATE → "DATE"
    10. NUMERIC → "NUMERIC"
    
    Confidence = (match_count / non_null_count) if > 0.9 threshold.
    """
    quoted = f'"{col_name}"'
    non_null_cnt = table_row_count - (conn.execute(f"SELECT COUNT(*) - COUNT({quoted}) FROM {full_table}")[0][0] or 0)
    
    if non_null_cnt <= 0:
        return None, 0.0, 0
    
    # For text-based patterns, sample or scan column
    # To avoid huge scans, sample up to 5000 rows
    sample_sql = f"SELECT {quoted} FROM {full_table} WHERE {quoted} IS NOT NULL LIMIT 5000"
    try:
        sample_rows = conn.execute(sample_sql)
        samples = [str(r[0]).strip() if r[0] else '' for r in sample_rows]
    except Exception:
        samples = []
    
    if not samples:
        return None, 0.0, 0
    
    # Test each pattern. Henkilötunnus (a person's ID) and Y-Tunnus (a company's ID) are
    # deliberately SEPARATE pattern names, never merged as both being "PII" — a business ID
    # is not personal data, and must never be eligible for the PII badge at all.
    pattern_tests = [
        ('PII', _detect_pii_henkilotunnus),
        ('BUSINESS_ID', _detect_pii_ytunnus),
        ('IBAN', _detect_iban),
        ('LEI', _detect_lei),
        ('BIC', _detect_bic),
        ('EMAIL', _detect_email),
        ('URL', _detect_url),
        ('PHONE', _detect_phone),
        ('UUID', lambda v: len(v) == 36 and v[8] == '-' and v[13] == '-' and v[18] == '-' and v[23] == '-'),
        ('DATE', lambda v: _try_parse_date(v)),
        ('NUMERIC', lambda v: _try_parse_numeric(v)),
    ]
    
    best_pattern = None
    best_confidence = 0.0
    best_invalid_count = 0
    
    for pattern_name, validator in pattern_tests:
        match_count = 0
        for sample in samples:
            if not sample:
                continue
            try:
                if validator(sample):
                    match_count += 1
            except Exception:
                pass
        
        confidence = match_count / len(samples) if samples else 0.0
        if confidence > 0.9:
            best_pattern = pattern_name
            best_confidence = confidence
            best_invalid_count = len(samples) - match_count
            break  # Take first match (highest priority)
    
    return best_pattern, best_confidence, best_invalid_count


_VALIDATOR_SAMPLE_LIMIT = 1000  # DISTINCT values to sample for validator pass-rate computation

# Maps inferred_pattern names to the vocabulary validator names that should be run
_PATTERN_TO_VALIDATOR = {
    "IBAN": "mod97",
    "LEI":  "lei_checksum",
    "BIC":  "bic_structure",
    "EMAIL": "email_format",
    "PHONE": "phone_format",
    "PII": "hetu_checksum",
    "BUSINESS_ID": "y_tunnus_checksum",
}

# Maps column name substrings to validators — allows proactive validator runs even
# when inferred_pattern didn't fire (e.g. a column named 'currency' gets iso4217)
_NAME_TOKEN_TO_VALIDATOR = {
    "iban":       "mod97",
    "lei":        "lei_checksum",
    "bic":        "bic_structure",
    "swift":      "bic_structure",
    "isin":       "isin_checksum",
    "currency":   "iso4217",
    "ccy":        "iso4217",
    "curr":       "iso4217",
    "country":    "iso3166",
    "jurisdiction": "iso3166",
    "email":      "email_format",
    "mail":       "email_format",
    "phone":      "phone_format",
    "mobile":     "phone_format",
    "telephone":  "phone_format",
    "hetu":       "hetu_checksum",
    "henkilotunnus": "hetu_checksum",
    "ytunnus":    "y_tunnus_checksum",
    "y_tunnus":   "y_tunnus_checksum",
}


def _compute_validator_pass_rates(
    conn,
    full_table: str,
    col_name: str,
    inferred_pattern: str | None,
) -> dict[str, float]:
    """Compute named-validator pass rates for a column at profiling time.

    Runs validators against up to _VALIDATOR_SAMPLE_LIMIT distinct non-null values
    from the live DB — far more accurate than re-running on 20 stored sample values.
    Returns a dict {validator_name: pass_rate} for every relevant validator.
    """
    from core.type_validators import run_validator  # local import to avoid circular dep

    # Determine which validators to run for this column
    validators_to_run: set[str] = set()

    # 1. From the inferred_pattern (if any)
    if inferred_pattern:
        v = _PATTERN_TO_VALIDATOR.get(inferred_pattern.upper())
        if v:
            validators_to_run.add(v)

    # 2. From column name tokens
    col_lower = col_name.lower()
    for token, validator_name in _NAME_TOKEN_TO_VALIDATOR.items():
        if token in col_lower:
            validators_to_run.add(validator_name)

    if not validators_to_run:
        return {}

    # Fetch up to 1000 distinct non-null values
    quoted = f'"{col_name}"'
    try:
        rows = conn.execute(
            f"SELECT DISTINCT CAST({quoted} AS VARCHAR) FROM {full_table} "
            f"WHERE {quoted} IS NOT NULL LIMIT {_VALIDATOR_SAMPLE_LIMIT}"
        )
        samples = [str(r[0]).strip() for r in rows if r[0] is not None]
    except Exception:
        return {}

    if not samples:
        return {}

    result: dict[str, float] = {}
    for validator_name in sorted(validators_to_run):
        try:
            rate = run_validator(validator_name, samples)
            if rate is not None:
                result[validator_name] = round(rate, 4)
        except Exception:
            pass

    return result


def _try_parse_date(value: str) -> bool:
    """Simple date check: looks like ISO date YYYY-MM-DD or similar."""
    if not value:
        return False
    return re.match(r'^\d{4}-\d{2}-\d{2}', value) is not None


def _try_parse_numeric(value: str) -> bool:
    """Simple numeric check: can be cast to float."""
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _sanitize_numbers(obj):
    """Recursively replace non-finite float values (inf, -inf, nan) with None."""
    if isinstance(obj, dict):
        return {k: _sanitize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_numbers(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


# ---------------------------------------------------------------------------
# Constraint extraction (delegated to connector)
# ---------------------------------------------------------------------------


def fetch_constraints(conn, schema_name: str) -> dict[str, dict]:
    """
    Return a dict keyed by table_name containing:
        {"primary_key": [col, ...], "foreign_keys": [col, ...], "relations": [{reference_table, columns, reference_table_columns}]}

    - foreign_keys: flat list of column names that are foreign keys
    - relations: detailed relationship info

    Delegates to the connector's fetch_constraints() method, which provides
    database-specific constraint extraction.
    """
    return conn.fetch_constraints(schema_name)


# ---------------------------------------------------------------------------
# Name/type-based FK inference — for sources with no DB-declared FOREIGN KEY
# constraints (e.g. flat ingested/raw schemas). Runs across all tables in a
# schema after each has been individually enriched, so PK/inferred-PK and
# column data types are already known. Applies uniformly to every source;
# results are always kept separate from `relations` (DB-declared) so the UI
# can label them distinctly and this never gets mistaken for an enforced
# constraint.
# ---------------------------------------------------------------------------

_ID_SUFFIXES = ("_id", "_key", "_no", "_num", "_code")
_GENERIC_KEY_NAMES = {"id", "key", "code", "no", "num", "pk"}


def _strip_id_suffix(name: str) -> str | None:
    """Strip a trailing identifier suffix (_id, _key, _no, _num, _code) from a
    column name, returning the semantic "stem". Returns None if the column has
    no recognized identifier suffix (e.g. a plain descriptive/flag column like
    'collateral_flag') — such columns are never stem-matched (table_reference /
    abbreviation), only ever considered for an exact-name match against
    another table's key column.
    """
    n = (name or "").strip().lower()
    for suf in _ID_SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            return n[: -len(suf)]
    return None


def _singularize(word: str) -> str:
    """Best-effort naive singularization of a snake_case token."""
    w = (word or "").lower()
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith(("ses", "xes", "ches", "shes")) and len(w) > 2:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 1:
        return w[:-1]
    return w


def _type_bucket(data_type: str | None) -> str:
    """Coarse type family so name matches aren't accepted across incompatible types."""
    dt = (data_type or "").upper()
    if any(t in dt for t in ("INT", "NUMERIC", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT")):
        return "numeric"
    if any(t in dt for t in ("VARCHAR", "TEXT", "STRING", "CHAR", "CLOB", "UUID")):
        return "text"
    if any(t in dt for t in ("DATE", "TIME")):
        return "temporal"
    return "other"


def _infer_relations_for_schema(tables: list[dict]) -> None:
    """Infer FK-like relationships by column-name + type matching, for columns
    with no DB-declared relation, and attach them as `inferred_relations` on
    each table dict (in place). Never modifies `relations` or `foreign_keys` —
    those remain the DB-declared-only source of truth.

    Only single-column keys are considered (composite keys are out of scope
    for this heuristic). A key registry is built from each table's declared
    `primary_key` (preferred) or `inferred_primary_key` (fallback).
    """
    # Build the key registry: one entry per table with a single-column key.
    registry: list[dict] = []
    for tbl in tables:
        tname = tbl.get("table_name") or tbl.get("name") or ""
        key_cols = tbl.get("primary_key") or tbl.get("inferred_primary_key") or []
        if len(key_cols) != 1:
            continue
        key_col = key_cols[0]
        col_dict = next((c for c in tbl.get("columns", []) if c.get("name") == key_col), {})
        tokens = [t for t in tname.lower().split("_") if t]
        registry.append({
            "table": tname,
            "key_col": key_col,
            "key_dtype": col_dict.get("data_type"),
            "last_token": tokens[-1] if tokens else tname.lower(),
        })

    for tbl in tables:
        tname = tbl.get("table_name") or tbl.get("name") or ""
        key_cols = set(tbl.get("primary_key") or tbl.get("inferred_primary_key") or [])
        declared_fk_cols = {
            col for rel in (tbl.get("relations") or []) for col in (rel.get("columns") or [])
        }
        inferred: list[dict] = []

        for col in tbl.get("columns", []):
            col_name = col.get("name") or ""
            if not col_name or col_name in key_cols or col_name in declared_fk_cols:
                continue
            stem = _strip_id_suffix(col_name)  # None if no recognized ID suffix
            col_bucket = _type_bucket(col.get("data_type"))

            best = None  # best candidate match so far: (rank, entry, basis)
            for entry in registry:
                if entry["table"] == tname:
                    continue  # never match a table against itself
                key_bucket = _type_bucket(entry["key_dtype"])
                if col_bucket != "other" and key_bucket != "other" and col_bucket != key_bucket:
                    continue  # incompatible data types — skip

                basis = None
                rank = None
                # Bare generic key names (e.g. two unrelated tables both having a
                # column literally called "id") are never a meaningful signal on
                # their own — require the column's own name to be specific.
                if (
                    col_name.lower() == entry["key_col"].lower()
                    and entry["key_col"].lower() not in _GENERIC_KEY_NAMES
                ):
                    basis, rank = "exact_name", 0
                elif stem:
                    singular_last = _singularize(entry["last_token"])
                    if stem == singular_last or stem == entry["last_token"]:
                        basis, rank = "table_reference", 1
                    elif len(stem) >= 3 and (
                        singular_last.startswith(stem) or stem.startswith(singular_last[: max(3, len(stem))])
                    ):
                        basis, rank = "abbreviation", 2

                if basis and (best is None or rank < best[0]):
                    best = (rank, entry, basis)

            if best is not None:
                _, entry, basis = best
                inferred.append({
                    "column": col_name,
                    "reference_table": entry["table"],
                    "reference_column": entry["key_col"],
                    "basis": basis,
                    "confidence": "high" if basis in ("exact_name", "table_reference") else "medium",
                })

        tbl["inferred_relations"] = inferred


def _compute_inferred_orphan_counts(conn, tables: list[dict]) -> None:
    """Attach an `orphan_count` to each inferred_relations entry (in place),
    using the same anti-join approach as the declared-relation orphan count
    in `_enrich_table`. Must run after `_infer_relations_for_schema` has
    populated `inferred_relations` on each table dict.
    """
    for tbl in tables:
        if tbl.get("row_count") is None:
            continue
        schema_name = tbl.get("schema_name")
        table_name = tbl.get("table_name")
        child_full = f'"{schema_name}"."{table_name}"'
        for rel in tbl.get("inferred_relations", []) or []:
            fk_col = rel.get("column")
            ref_table = rel.get("reference_table")
            ref_col = rel.get("reference_column")
            if not fk_col or not ref_table or not ref_col:
                continue
            parent_full = f'"{schema_name}"."{ref_table}"'
            sql = (
                f'SELECT SUM(CASE WHEN p."{ref_col}" IS NULL AND c."{fk_col}" IS NOT NULL THEN 1 ELSE 0 END) '
                f'FROM {child_full} c LEFT JOIN {parent_full} p ON c."{fk_col}" = p."{ref_col}"'
            )
            try:
                rel["orphan_count"] = int(conn.execute(sql)[0][0] or 0)
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Stats enrichment
# ---------------------------------------------------------------------------

_MAX_SAMPLE_VALUES = 20   # stored in catalog YAML; used by semantic validator and UI
_TOP_FREQ = 10            # top-N frequent values for coded/reference columns


def _enrich_column(conn, full_table: str, col: dict, table_row_count: int) -> dict:
    """Return a ColumnProfile-shaped dict for *col*."""
    col_name = col["name"]
    quoted = f'"{col_name}"'

    profile: dict = {
        "name": col_name,
        "description": col.get("description"),
        "data_type": col.get("data_type"),
        "row_count": table_row_count,
        "null_count": None,
        "null_pct": None,
        "distinct_count": None,
        "min_value": None,
        "max_value": None,
        "sample_values": [],
        # Enhanced metrics (may be None if not computed)
        "uniqueness_pct": None,
        "duplicate_count": None,
        "empty_string_count": None,
        "placeholder_count": None,
        "length_min": None,
        "length_max": None,
        "length_avg": None,
        "top_values": [],
        "code_values": None,
        "value_distribution": None,
        "inferred_pattern": None,
        "pattern_confidence": None,
        "invalid_format_count": None,
        "numeric_avg": None,
        "numeric_median": None,
        "numeric_stddev": None,
        "numeric_outlier_count": None,
        "outlier_detection": None,
        "decimal_scale_distribution": None,
        "future_date_count": None,
        "suspicious_date_count": None,
        "type_mismatch_count": None,
    }

    try:
        null_count, distinct_count = conn.execute(f"""
            SELECT
                COUNT(*) - COUNT({quoted})  AS null_count,
                COUNT(DISTINCT {quoted})    AS distinct_count
            FROM {full_table}
        """)[0]
        profile["null_count"] = int(null_count)
        profile["null_pct"] = (
            round(int(null_count) / table_row_count, 4) if table_row_count else 0.0
        )
        profile["distinct_count"] = int(distinct_count)
    except Exception as exc:
        profile["stats_error"] = str(exc)
        return profile

    try:
        row = conn.execute(f"""
            SELECT MIN({quoted}), MAX({quoted}) FROM {full_table}
        """)[0]
        profile["min_value"] = str(row[0]) if row[0] is not None else None
        profile["max_value"] = str(row[1]) if row[1] is not None else None
    except Exception:
        pass

    try:
        rows = conn.execute(f"""
            SELECT DISTINCT {quoted}
            FROM {full_table}
            WHERE {quoted} IS NOT NULL
            ORDER BY {quoted}
            LIMIT {_MAX_SAMPLE_VALUES}
        """)
        profile["sample_values"] = [str(r[0]) for r in rows]
    except Exception:
        pass

    # Additional derived metrics
    try:
        # uniqueness %, duplicate count
        if table_row_count and profile.get("distinct_count") is not None:
            profile["uniqueness_pct"] = round(profile["distinct_count"] / table_row_count, 4) if table_row_count else None
            profile["duplicate_count"] = max(0, table_row_count - int(profile["distinct_count"]))
    except Exception:
        pass

    try:
        # empty string count and placeholder values
        placeholders = ["UNKNOWN", "N/A", "NA", "9999", "1900-01-01"]
        ph_cond = " OR ".join([f"UPPER(TRIM({quoted})) = '{p}'" for p in placeholders if p])
        empty_sql = f"SELECT SUM(CASE WHEN {quoted} = '' THEN 1 ELSE 0 END) FROM {full_table}"
        ph_sql = f"SELECT SUM(CASE WHEN ({ph_cond}) THEN 1 ELSE 0 END) FROM {full_table}" if ph_cond else None
        empty_cnt = conn.execute(empty_sql)[0][0]
        profile["empty_string_count"] = int(empty_cnt or 0)
        if ph_sql:
            ph_cnt = conn.execute(ph_sql)[0][0]
            profile["placeholder_count"] = int(ph_cnt or 0)
    except Exception:
        pass

    try:
        # length stats (cast to varchar safely)
        len_sql = f"SELECT MIN(LENGTH(CAST({quoted} AS VARCHAR))), MAX(LENGTH(CAST({quoted} AS VARCHAR))), AVG(LENGTH(CAST({quoted} AS VARCHAR))) FROM {full_table} WHERE {quoted} IS NOT NULL"
        lm, lx, la = conn.execute(len_sql)[0]
        profile["length_min"] = int(lm) if lm is not None else None
        profile["length_max"] = int(lx) if lx is not None else None
        profile["length_avg"] = float(la) if la is not None else None
    except Exception:
        pass

    try:
        # top N frequent values
        tf_rows = conn.execute(f"SELECT {quoted} AS v, COUNT(*) AS cnt FROM {full_table} GROUP BY {quoted} ORDER BY cnt DESC LIMIT {_TOP_FREQ}")
        profile["top_values"] = [{"value": r[0], "count": int(r[1])} for r in tf_rows]
    except Exception:
        pass

    try:
        # Full code list (U0 Task 6.1): ALL distinct values with true frequencies,
        # via a real GROUP BY — unlike sample_values (capped at 20) and top_values
        # (capped at _TOP_FREQ), this is a complete list for genuinely low-cardinality
        # columns. Only computed when distinct_count is small enough that a full
        # code list is a meaningful "coded" archetype signal.
        distinct_count = profile.get("distinct_count")
        if distinct_count is not None and distinct_count <= 50:
            code_rows = conn.execute(
                f"SELECT {quoted} AS v, COUNT(*) AS cnt FROM {full_table} "
                f"WHERE {quoted} IS NOT NULL GROUP BY {quoted} ORDER BY cnt DESC"
            )
            profile["code_values"] = [{"value": r[0], "count": int(r[1])} for r in code_rows]
    except Exception:
        pass

    try:
        # numeric summary if castable
        num_rows = conn.execute(f"SELECT AVG(TRY_CAST({quoted} AS DOUBLE)), percentile_cont(0.5) WITHIN GROUP (ORDER BY TRY_CAST({quoted} AS DOUBLE)), STDDEV(TRY_CAST({quoted} AS DOUBLE)) FROM {full_table} WHERE {quoted} IS NOT NULL")
        if num_rows:
            navg, nmed, nstd = num_rows[0]
            profile["numeric_avg"] = float(navg) if navg is not None else None
            profile["numeric_median"] = float(nmed) if nmed is not None else None
            profile["numeric_stddev"] = float(nstd) if nstd is not None else None
            if profile["numeric_avg"] is not None and profile["numeric_stddev"] is not None:
                # Two-sided outliers (U0 Task 6.2): beyond mean ± 3*stddev in
                # either direction. Previously only the upper bound (> mean +
                # 3*stddev) was checked, silently missing negative-direction
                # outliers. The marker below lets consumers (and the
                # assessment fingerprint) tell two-sided results apart from
                # any older one-sided cached value.
                upper = profile["numeric_avg"] + 3 * profile["numeric_stddev"]
                lower = profile["numeric_avg"] - 3 * profile["numeric_stddev"]
                out_cnt = conn.execute(
                    f"SELECT SUM(CASE WHEN TRY_CAST({quoted} AS DOUBLE) > {upper} "
                    f"OR TRY_CAST({quoted} AS DOUBLE) < {lower} THEN 1 ELSE 0 END) FROM {full_table}"
                )[0][0]
                profile["numeric_outlier_count"] = int(out_cnt or 0)
                profile["outlier_detection"] = "two_sided"
    except Exception:
        pass

    try:
        # Decimal-scale distribution (U0 Task 6.3): share of non-null values at
        # each observed decimal scale (digits after the decimal point). Reuses
        # the same TRY_CAST(... AS DOUBLE) values as the numeric summary above.
        # Consumed by core.shape_detectors.decimal_scale_consistent.
        scale_rows = conn.execute(
            f"SELECT CASE WHEN STRPOS(CAST(TRY_CAST({quoted} AS DOUBLE) AS VARCHAR), '.') = 0 THEN 0 "
            f"ELSE LENGTH(CAST(TRY_CAST({quoted} AS DOUBLE) AS VARCHAR)) "
            f"- STRPOS(CAST(TRY_CAST({quoted} AS DOUBLE) AS VARCHAR), '.') END AS scale, "
            f"COUNT(*) AS cnt "
            f"FROM {full_table} "
            f"WHERE {quoted} IS NOT NULL AND TRY_CAST({quoted} AS DOUBLE) IS NOT NULL "
            f"GROUP BY 1"
        )
        total = sum(int(r[1]) for r in scale_rows) if scale_rows else 0
        if total:
            profile["decimal_scale_distribution"] = {
                int(r[0]): round(int(r[1]) / total, 4) for r in scale_rows
            }
    except Exception:
        pass

    try:
        # date heuristics
        # future dates
        future_cnt = conn.execute(f"SELECT SUM(CASE WHEN TRY_CAST({quoted} AS DATE) > CURRENT_DATE THEN 1 ELSE 0 END) FROM {full_table} WHERE {quoted} IS NOT NULL")[0][0]
        profile["future_date_count"] = int(future_cnt or 0)
        # suspicious early dates before 1900-01-01
        susp_cnt = conn.execute(f"SELECT SUM(CASE WHEN TRY_CAST({quoted} AS DATE) < DATE '1900-01-01' THEN 1 ELSE 0 END) FROM {full_table} WHERE {quoted} IS NOT NULL")[0][0]
        profile["suspicious_date_count"] = int(susp_cnt or 0)
    except Exception:
        pass

    try:
        # inferred pattern: text-column-only detection for IBAN, LEI, BIC, Phone, Email, URL, PII, plus UUID/DATE/NUMERIC
        data_type = col.get("data_type", "").upper() if col.get("data_type") else ""
        if _is_text_column(data_type):
            pattern_name, confidence, invalid_count = _detect_pattern_in_column(conn, full_table, col_name, data_type, table_row_count)
            if pattern_name:
                profile["inferred_pattern"] = pattern_name
                profile["pattern_confidence"] = round(confidence, 4)
                profile["invalid_format_count"] = invalid_count
        else:
            # For non-text columns, still check UUID, DATE, NUMERIC as fallback
            uuid_check = conn.execute(f"SELECT SUM(CASE WHEN LENGTH({quoted}) = 36 AND SUBSTR({quoted},9,1)='-' AND SUBSTR({quoted},14,1)='-' AND SUBSTR({quoted},19,1)='-' AND SUBSTR({quoted},24,1)='-' THEN 1 ELSE 0 END) FROM {full_table} WHERE {quoted} IS NOT NULL")[0][0]
            uuid_cnt = int(uuid_check or 0)
            non_null_cnt = table_row_count - (profile.get("null_count") or 0)
            if non_null_cnt and uuid_cnt / non_null_cnt > 0.9:
                profile["inferred_pattern"] = "UUID"
                profile["pattern_confidence"] = round(uuid_cnt / non_null_cnt, 4)
            else:
                # date-like check
                date_ok = conn.execute(f"SELECT SUM(CASE WHEN TRY_CAST({quoted} AS DATE) IS NOT NULL THEN 1 ELSE 0 END) FROM {full_table} WHERE {quoted} IS NOT NULL")[0][0]
                date_ok = int(date_ok or 0)
                if non_null_cnt and date_ok / non_null_cnt > 0.9:
                    profile["inferred_pattern"] = "DATE"
                    profile["pattern_confidence"] = round(date_ok / non_null_cnt, 4)
                else:
                    # numeric-like
                    num_ok = conn.execute(f"SELECT SUM(CASE WHEN TRY_CAST({quoted} AS DOUBLE) IS NOT NULL THEN 1 ELSE 0 END) FROM {full_table} WHERE {quoted} IS NOT NULL")[0][0]
                    num_ok = int(num_ok or 0)
                    if non_null_cnt and num_ok / non_null_cnt > 0.9:
                        profile["inferred_pattern"] = "NUMERIC"
                        profile["pattern_confidence"] = round(num_ok / non_null_cnt, 4)
    except Exception:
        pass

    try:
        # Validator pass rates — computed against up to 1000 DISTINCT live DB values.
        # These are stored in the catalog YAML and consumed by the semantic resolver
        # so it never needs to re-run validators on the small sample_values list.
        vpr = _compute_validator_pass_rates(
            conn, full_table, col_name, profile.get("inferred_pattern")
        )
        if vpr:
            profile["validator_pass_rates"] = vpr
    except Exception:
        pass

    try:
        # invalid format / type mismatch count relative to declared data_type
        dt = col.get("data_type", "").upper() if col.get("data_type") else ""
        mismatch = None
        if dt.startswith("DATE"):
            mismatch = conn.execute(f"SELECT SUM(CASE WHEN {quoted} IS NOT NULL AND TRY_CAST({quoted} AS DATE) IS NULL THEN 1 ELSE 0 END) FROM {full_table}")[0][0]
        elif dt.startswith("INT") or dt.startswith("DEC") or dt.startswith("NUM") or dt.startswith("BIGINT"):
            mismatch = conn.execute(f"SELECT SUM(CASE WHEN {quoted} IS NOT NULL AND TRY_CAST({quoted} AS DOUBLE) IS NULL THEN 1 ELSE 0 END) FROM {full_table}")[0][0]
        if mismatch is not None:
            profile["type_mismatch_count"] = int(mismatch or 0)
    except Exception:
        pass

    return profile


def _enrich_table(conn, schema_name: str, table: dict, constraints: dict) -> dict:
    # Support multiple catalog table name keys: prefer `table_name`, then `name`, then `table`
    table_name = table.get("table_name") or table.get("name") or table.get("table")
    full_table = f'"{schema_name}"."{table_name}"'
    tbl_constraints = constraints.get(table_name, {})

    # Prefer a schema-qualified reference if the connector exposes that schema/table.
    resolved_table = None
    last_exc = None
    try:
        db_schemas = conn.get_schemas()
    except Exception:
        db_schemas = []

    # Try exact schema match first (case-insensitive), then look for table in any schema
    try:
        matched_schema = None
        for s in db_schemas:
            if s.get("name", "").lower() == (schema_name or "").lower():
                matched_schema = s
                break
        if matched_schema:
            tbl_names = [t.get("name") for t in matched_schema.get("tables", [])]
            if table_name in tbl_names or table_name.lower() in [n.lower() for n in (tbl_names or [])]:
                candidate = f'"{matched_schema.get("name")}"."{table_name}"'
                row_count = int(conn.execute(f"SELECT COUNT(*) FROM {candidate}")[0][0])
                resolved_table = candidate
        if not resolved_table:
            # search across schemas for a matching table name
            for s in db_schemas:
                tbl_names = [t.get("name") for t in s.get("tables", [])]
                for n in tbl_names:
                    if n and n.lower() == table_name.lower():
                        candidate = f'"{s.get("name")}"."{n}"'
                        try:
                            row_count = int(conn.execute(f"SELECT COUNT(*) FROM {candidate}")[0][0])
                            resolved_table = candidate
                            break
                        except Exception:
                            continue
                if resolved_table:
                    break
    except Exception:
        resolved_table = None

    # fallback: try common unqualified/quoted forms
    if resolved_table is None:
        candidates = [f'"{schema_name}"."{table_name}"', f'"{table_name}"', table_name]
        for cand in candidates:
            try:
                row_count = int(conn.execute(f"SELECT COUNT(*) FROM {cand}")[0][0])
                resolved_table = cand
                break
            except Exception as exc:
                last_exc = exc
    if resolved_table is None:
        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "description": table.get("description"),
            "row_count": None,
            "primary_key": tbl_constraints.get("primary_key", []),
            "inferred_primary_key": [],
            "foreign_keys": tbl_constraints.get("foreign_keys", []),
            "relations": tbl_constraints.get("relations", []),
            "row_count_error": f"Catalog Error: Table with name \"{schema_name}.{table_name}\" does not exist because {last_exc}",
            "columns": [],
        }

    columns = [
        _enrich_column(conn, resolved_table, col, row_count)
        for col in table.get("columns", [])
    ]

    # ---------------------------------------------------------------------------
    # Heuristic primary-key inference for tables with no declared PK constraint
    # ---------------------------------------------------------------------------
    # A column is a candidate key if every non-null value is unique AND there are
    # no nulls at all.  We never overwrite a declared PK — only fill the gap.
    declared_pk = tbl_constraints.get("primary_key", [])
    inferred_primary_key: list[str] = []
    if not declared_pk and row_count and row_count > 1:
        for col_profile in columns:
            null_pct  = col_profile.get("null_pct")
            uniq_pct  = col_profile.get("uniqueness_pct")
            if null_pct == 0.0 and uniq_pct == 1.0:
                inferred_primary_key.append(col_profile["name"])

    # Use whichever PK set is available for the duplicate-count query below
    effective_pk = declared_pk or inferred_primary_key

    # Table-level derived metrics
    duplicate_count = None
    duplicate_pct = None
    try:
        pk = effective_pk
        if pk:
            pk_list = ", ".join([f'"{c}"' for c in pk])
            dup_sql = f"SELECT COUNT(*) - COUNT(DISTINCT {pk_list}) FROM {resolved_table}"
            dup_cnt = conn.execute(dup_sql)[0][0]
            duplicate_count = int(dup_cnt or 0)
            duplicate_pct = round(duplicate_count / row_count, 4) if row_count else None
    except Exception:
        duplicate_count = None

    orphan_fk_count = 0
    try:
        for rel in tbl_constraints.get("relations", []):
            ref_table = rel.get("reference_table")
            fk_cols = rel.get("columns", [])
            ref_cols = rel.get("reference_table_columns", [])
            if not ref_table or not fk_cols or not ref_cols:
                continue
            # build join condition
            child_alias = "c"
            parent_alias = "p"
            join_conds = []
            where_conds = []
            for fk, rc in zip(fk_cols, ref_cols):
                join_conds.append(f"{child_alias}.\"{fk}\" = {parent_alias}.\"{rc}\"")
                where_conds.append(f"{child_alias}.\"{fk}\" IS NOT NULL")
            join_on = " AND ".join(join_conds)
            where_clause = " AND ".join(where_conds)
            parent_full = f'"{schema_name}"."{ref_table}"'
            sql = f"SELECT SUM(CASE WHEN {parent_alias}.\"{ref_cols[0]}\" IS NULL AND ({where_clause}) THEN 1 ELSE 0 END) FROM {resolved_table} {child_alias} LEFT JOIN {parent_full} {parent_alias} ON {join_on}"
            try:
                cnt = int(conn.execute(sql)[0][0] or 0)
                rel["orphan_count"] = cnt
                orphan_fk_count += cnt
            except Exception:
                continue
    except Exception:
        orphan_fk_count = None

    # completeness and description coverage
    try:
        non_null_cols = [c for c in columns if c.get("null_pct") is not None]
        if non_null_cols:
            completeness_vals = [1.0 - (c.get("null_pct") or 0.0) for c in non_null_cols]
            completeness_summary = sum(completeness_vals) / len(completeness_vals)
        else:
            completeness_summary = None
    except Exception:
        completeness_summary = None

    try:
        total_cols = len(table.get("columns", []))
        described = sum(1 for c in table.get("columns", []) if c.get("description"))
        pct_columns_described = described / total_cols if total_cols else None
    except Exception:
        pct_columns_described = None

    result = {
        "schema_name": schema_name,
        "table_name": table_name,
        "description": table.get("description"),
        "row_count": row_count,
        "primary_key": declared_pk,
        "inferred_primary_key": inferred_primary_key,
        "foreign_keys": tbl_constraints.get("foreign_keys", []),
        "relations": tbl_constraints.get("relations", []),
        "columns": columns,
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "orphan_fk_count": orphan_fk_count,
        "completeness_summary": completeness_summary,
        "pct_columns_described": pct_columns_described,
    }

    # sanitize numeric edge-cases (Infinity/NaN) to avoid JSON serialization errors
    return _sanitize_numbers(result)


def enrich_schemas(conn, schemas: list[dict]) -> list[dict]:
    """Enrich all schemas with row counts, column stats, and constraints."""
    result = []
    for schema in schemas:
        schema_name = schema["name"]
        constraints = fetch_constraints(conn, schema_name)
        tables = []
        for tbl in schema.get("tables", []):
            tname = tbl.get("table_name") or tbl.get("name") or tbl.get("table")
            try:
                # safe debug print
                print(f"    {schema_name}.{tname} ...")
            except Exception:
                pass
            tables.append(_enrich_table(conn, schema_name, tbl, constraints))
        # Second pass — infer name/type-matched relationships across this schema's
        # tables for any column not already covered by a DB-declared relation.
        _infer_relations_for_schema(tables)
        _compute_inferred_orphan_counts(conn, tables)
        result.append({**schema, "tables": tables})
    return result
