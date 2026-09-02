"""Smart Data Assessment (SDA) — deterministic findings layer.

This module turns the *facts* already computed by ``core.extractors.profiler``
into a list of advisory **findings**. Findings are observations, not enforced
business rules: they highlight what evidently appears in the data so a user can
make an informed onboarding decision. Nothing here blocks data onboarding.

Phase 1 is purely deterministic (``source="rule"``). An AI-suggested generator
can later emit findings using the same shape and be merged into the same list.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# Severity ordering used for summary roll-ups (higher = more important).
_SEVERITY_RANK = {"info": 0, "attention": 1, "high": 2}

# In-memory cache of AI-suggested findings, keyed by a profile fingerprint.
# A fingerprint change (e.g. after re-onboarding new data) naturally misses the
# cache and triggers fresh generation, so suggestions never go stale.
_AI_CACHE: dict[str, list[dict[str, Any]]] = {}

# Column fact fields that define the AI fingerprint. Only data-shaping facts are
# included so cosmetic metadata changes do not needlessly invalidate the cache.
_FINGERPRINT_COL_FIELDS = (
    "name", "data_type", "null_pct", "distinct_count", "uniqueness_pct",
    "placeholder_count", "empty_string_count", "inferred_pattern",
    "invalid_format_count", "type_mismatch_count", "future_date_count",
    "suspicious_date_count", "numeric_outlier_count",
    # U0 Task 7: numeric_outlier_count semantics changed (one-sided -> two-sided
    # outlier detection, core/extractors/profiler.py). This marker field flips
    # from None to "two_sided" on the next re-profile, forcing exactly one
    # re-assessment per already-profiled numeric column so the semantics change
    # is picked up. Do NOT add code_values/decimal_scale_distribution here — no
    # assessment consumer reads them yet; DQ fingerprints its own inputs in U2.
    "outlier_detection",
)
_FINGERPRINT_TABLE_FIELDS = (
    "schema_name", "table_name", "row_count", "duplicate_count",
    "orphan_fk_count", "inferred_primary_key",
)

# Patterns that carry a regulatory identifier meaning. When these fail format
# validation we add a short regulatory framing to the finding.
_REGULATORY_PATTERNS = {
    "IBAN": "Account identifiers must be valid for regulatory reporting (e.g. CRR/COREP exposures).",
    "LEI": "Legal Entity Identifiers (ISO 17442) are required to identify counterparties in regulatory submissions.",
    "BIC": "BIC/SWIFT codes identify financial institutions and must be well-formed for cross-border reporting.",
}


def _finding(
    *,
    scope: str,
    target: str,
    severity: str,
    category: str,
    title: str,
    rationale: str,
    evidence: dict[str, Any],
    regulatory_note: str | None = None,
    source: str = "rule",
) -> dict[str, Any]:
    finding = {
        "scope": scope,
        "target": target,
        "severity": severity,
        "category": category,
        "title": title,
        "rationale": rationale,
        "evidence": evidence,
        "source": source,
    }
    if regulatory_note:
        finding["regulatory_note"] = regulatory_note
    return finding


def _pct(part: int | None, whole: int | None) -> float | None:
    if not whole or part is None:
        return None
    return part / whole


def _assess_column(col: dict[str, Any], pk_cols: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    name = col.get("name", "?")
    target = name
    row_count = col.get("row_count") or 0

    # --- Completeness ---------------------------------------------------
    null_pct = col.get("null_pct")
    if null_pct is not None and null_pct >= 0.5:
        severity = "high" if null_pct >= 0.9 else "attention"
        findings.append(_finding(
            scope="column", target=target, severity=severity,
            category="completeness",
            title="High proportion of missing values",
            rationale=f"{round(null_pct * 100, 1)}% of values in '{name}' are NULL.",
            evidence={"null_pct": null_pct, "null_count": col.get("null_count")},
        ))

    placeholder_count = col.get("placeholder_count") or 0
    ph_pct = _pct(placeholder_count, row_count)
    if ph_pct is not None and ph_pct >= 0.1:
        findings.append(_finding(
            scope="column", target=target,
            severity="attention" if ph_pct >= 0.3 else "info",
            category="completeness",
            title="Placeholder values detected",
            rationale=(
                f"{placeholder_count} value(s) ({round(ph_pct * 100, 1)}%) in '{name}' "
                "look like placeholders (e.g. UNKNOWN, N/A, 9999, 1900-01-01)."
            ),
            evidence={"placeholder_count": placeholder_count, "placeholder_pct": ph_pct},
        ))

    empty_count = col.get("empty_string_count") or 0
    if empty_count > 0:
        findings.append(_finding(
            scope="column", target=target, severity="info",
            category="completeness",
            title="Empty strings present",
            rationale=f"{empty_count} value(s) in '{name}' are empty strings rather than NULL.",
            evidence={"empty_string_count": empty_count},
        ))

    # --- Validity -------------------------------------------------------
    pattern = col.get("inferred_pattern")
    invalid_count = col.get("invalid_format_count") or 0
    if pattern and invalid_count > 0:
        inv_pct = _pct(invalid_count, row_count)
        severity = "high" if (inv_pct or 0) >= 0.1 else "attention"
        findings.append(_finding(
            scope="column", target=target, severity=severity,
            category="regulatory" if pattern in _REGULATORY_PATTERNS else "validity",
            title=f"Values not matching expected {pattern} format",
            rationale=(
                f"'{name}' looks like a {pattern} column but {invalid_count} value(s) "
                f"do not match the expected {pattern} format."
            ),
            evidence={
                "inferred_pattern": pattern,
                "invalid_format_count": invalid_count,
                "invalid_format_pct": inv_pct,
                "pattern_confidence": col.get("pattern_confidence"),
            },
            regulatory_note=_REGULATORY_PATTERNS.get(pattern),
        ))

    type_mismatch = col.get("type_mismatch_count") or 0
    if type_mismatch > 0:
        findings.append(_finding(
            scope="column", target=target, severity="attention",
            category="validity",
            title="Values inconsistent with declared type",
            rationale=(
                f"{type_mismatch} value(s) in '{name}' cannot be cast to its declared "
                f"type ({col.get('data_type')})."
            ),
            evidence={"type_mismatch_count": type_mismatch, "data_type": col.get("data_type")},
        ))

    future_dates = col.get("future_date_count") or 0
    if future_dates > 0:
        findings.append(_finding(
            scope="column", target=target, severity="attention",
            category="validity",
            title="Future-dated values",
            rationale=f"{future_dates} value(s) in '{name}' are dated in the future.",
            evidence={"future_date_count": future_dates},
        ))

    suspicious_dates = col.get("suspicious_date_count") or 0
    if suspicious_dates > 0:
        findings.append(_finding(
            scope="column", target=target, severity="info",
            category="validity",
            title="Suspiciously early dates",
            rationale=f"{suspicious_dates} value(s) in '{name}' are dated before 1900-01-01.",
            evidence={"suspicious_date_count": suspicious_dates},
        ))

    # --- Uniqueness -----------------------------------------------------
    duplicate_count = col.get("duplicate_count") or 0
    if name in pk_cols and duplicate_count > 0:
        findings.append(_finding(
            scope="column", target=target, severity="high",
            category="uniqueness",
            title="Primary key has duplicate values",
            rationale=(
                f"'{name}' is part of the primary key but has {duplicate_count} "
                "duplicate value(s), which breaks row identity."
            ),
            evidence={"duplicate_count": duplicate_count, "uniqueness_pct": col.get("uniqueness_pct")},
        ))

    # --- Consistency ----------------------------------------------------
    outliers = col.get("numeric_outlier_count") or 0
    if outliers > 0:
        findings.append(_finding(
            scope="column", target=target, severity="info",
            category="consistency",
            title="Numeric outliers detected",
            rationale=(
                f"{outliers} value(s) in '{name}' lie beyond 3 standard deviations "
                "from the mean."
            ),
            evidence={"numeric_outlier_count": outliers},
        ))

    distinct_count = col.get("distinct_count")
    if distinct_count == 1 and row_count > 1:
        findings.append(_finding(
            scope="column", target=target, severity="info",
            category="consistency",
            title="Single constant value",
            rationale=f"Every non-null row of '{name}' holds the same value.",
            evidence={"distinct_count": distinct_count, "row_count": row_count},
        ))

    return findings


def _assess_table(profile: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    table_name = profile.get("table_name", "?")

    duplicate_count = profile.get("duplicate_count") or 0
    if duplicate_count > 0:
        dup_pct = profile.get("duplicate_pct")
        findings.append(_finding(
            scope="dataset", target=table_name, severity="high",
            category="uniqueness",
            title="Duplicate primary-key rows",
            rationale=(
                f"{duplicate_count} row(s) share a primary-key value, so rows are not "
                "uniquely identified."
            ),
            evidence={"duplicate_count": duplicate_count, "duplicate_pct": dup_pct},
        ))

    orphan_fk = profile.get("orphan_fk_count") or 0
    if orphan_fk > 0:
        findings.append(_finding(
            scope="dataset", target=table_name, severity="attention",
            category="consistency",
            title="Orphan foreign keys",
            rationale=(
                f"{orphan_fk} foreign-key value(s) have no matching parent record, "
                "indicating referential gaps."
            ),
            evidence={"orphan_fk_count": orphan_fk},
            regulatory_note=(
                "Unresolved references can break lineage and counterparty linkage in "
                "regulatory reporting."
            ),
        ))

    completeness = profile.get("completeness_summary")
    if completeness is not None and completeness < 0.8:
        findings.append(_finding(
            scope="dataset", target=table_name, severity="attention",
            category="completeness",
            title="Low overall completeness",
            rationale=(
                f"Average column completeness is {round(completeness * 100, 1)}%, below "
                "the 80% guideline."
            ),
            evidence={"completeness_summary": completeness},
        ))

    described = profile.get("pct_columns_described")
    if described is not None and described < 0.5:
        findings.append(_finding(
            scope="dataset", target=table_name, severity="info",
            category="metadata",
            title="Low description coverage",
            rationale=(
                f"Only {round(described * 100, 1)}% of columns have a description, "
                "limiting downstream understanding."
            ),
            evidence={"pct_columns_described": described},
        ))

    return findings


def _summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity = {"info": 0, "attention": 0, "high": 0}
    by_scope = {"dataset": 0, "column": 0}
    by_category: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        scope = f.get("scope", "column")
        by_scope[scope] = by_scope.get(scope, 0) + 1
        cat = f.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(findings),
        "by_severity": by_severity,
        "by_scope": by_scope,
        "by_category": by_category,
    }


def profile_fingerprint(profile: dict[str, Any]) -> str:
    """Return a stable hash of the data-shaping facts in *profile*.

    Used as the AI cache key: identical data shape => identical fingerprint =>
    cache hit; changed data => new fingerprint => regeneration.
    """
    payload: dict[str, Any] = {
        k: profile.get(k) for k in _FINGERPRINT_TABLE_FIELDS
    }
    payload["columns"] = [
        {k: col.get(k) for k in _FINGERPRINT_COL_FIELDS}
        for col in profile.get("columns", []) or []
    ]
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sort_findings(findings: list[dict[str, Any]]) -> None:
    findings.sort(
        key=lambda f: (
            -_SEVERITY_RANK.get(f.get("severity", "info"), 0),
            0 if f.get("scope") == "dataset" else 1,
            f.get("target", ""),
        )
    )


def assess_table(
    profile: dict[str, Any],
    *,
    include_ai: bool = False,
    refresh_ai: bool = False,
) -> dict[str, Any]:
    """Produce advisory findings for a profiled table.

    ``profile`` is the table-shaped dict returned by
    ``core.extractors.profiler.enrich_schemas`` (the same payload served by the
    Discovery ``/profile`` endpoint). Returns a dict with ``findings`` (sorted
    most-important first) and a ``summary`` roll-up.

    When ``include_ai`` is true, AI-suggested findings are merged in. They are
    cached by :func:`profile_fingerprint`; pass ``refresh_ai`` to bypass the
    cache. AI failures degrade gracefully — the deterministic findings are
    always returned and ``ai_status`` reports what happened.
    """
    pk_cols = set(profile.get("primary_key", []) or [])
    inferred_pk = list(profile.get("inferred_primary_key", []) or [])

    # If no declared PK exists, use heuristically inferred candidate keys for
    # duplicate detection AND emit an advisory finding so users know.
    if not pk_cols and inferred_pk:
        pk_cols = set(inferred_pk)

    findings = _assess_table(profile)

    # Emit an informational finding for each inferred candidate key so it is
    # visible in the Discovery observations panel.
    if inferred_pk and not profile.get("primary_key"):
        table_name = profile.get("table_name", "?")
        cols_str = ", ".join(inferred_pk)
        findings.append(_finding(
            scope="dataset",
            target=table_name,
            severity="info",
            category="metadata",
            title="No primary key declared — candidate key(s) inferred",
            rationale=(
                f"No formal PRIMARY KEY constraint is defined for this table. "
                f"The following column(s) appear to satisfy uniqueness and non-null criteria "
                f"and are being treated as candidate keys for quality checks: {cols_str}."
            ),
            evidence={"inferred_primary_key": inferred_pk},
        ))

    for col in profile.get("columns", []) or []:
        findings.extend(_assess_column(col, pk_cols))

    ai_status = "skipped"
    if include_ai:
        ai_status, ai_findings = _ai_findings(profile, refresh_ai)
        findings.extend(ai_findings)

    _sort_findings(findings)

    return {
        "table_name": profile.get("table_name"),
        "schema_name": profile.get("schema_name"),
        "findings": findings,
        "summary": _summarize(findings),
        "ai_status": ai_status,
    }


def _ai_findings(
    profile: dict[str, Any], refresh: bool
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(status, findings)`` for the AI layer, using the cache.

    ``status`` is one of ``cached``, ``generated``, or ``unavailable``.
    """
    key = profile_fingerprint(profile)
    if not refresh and key in _AI_CACHE:
        return "cached", list(_AI_CACHE[key])

    try:
        from agents.assessment_agent import generate_ai_findings
    except Exception:
        return "unavailable", []

    findings = generate_ai_findings(profile)
    if not findings:
        # Distinguish a clean empty result (cacheable) from an outright failure.
        # generate_ai_findings already swallows errors and returns [], so we
        # cache the empty result to avoid hammering the LLM on repeat views.
        _AI_CACHE[key] = []
        return "generated", []

    _AI_CACHE[key] = list(findings)
    return "generated", list(findings)
