"""Deterministic column archetype detection for DQ scoring.

An archetype decides *which* profiler signals are scored as quality defects
versus merely cited as evidence (DQ-Scoring-Model-Design-v1.md §3). Detection
is deterministic and precedence-ordered.

F1 precedence (SD × DQ integration contract §2-F1) puts two governed inputs
*ahead* of the profiler heuristics:

    0a. declared / inferred PK or declared FK-source  -> key_like
    0b. steward-ACCEPTED semantic type                -> mapped archetype
    1-6 existing profiler heuristics                  (fallback)

Only an *accepted* semantic type drives 0b — a machine guess alone
never does (a steward decision is truth, a rule guess is not). The
``SemanticTypeStore`` record is passed in by the caller (injected, never
imported here) so this module stays free of store/IO dependencies.
"""
from __future__ import annotations

from typing import Any

from core.dq_config import DQScoringConfig

ColumnDict = dict[str, Any]
TableDict = dict[str, Any]

ARCHETYPES = ("key_like", "coded", "date", "numeric", "text", "free_text")

_NUMERIC_TYPE_TOKENS = (
    "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL", "NUMBER",
    "BIGINT", "SMALLINT", "TINYINT", "INTEGER", "INT",
)
_DATE_TYPE_TOKENS = ("TIMESTAMP", "DATETIME", "DATE", "TIME")
_STRING_TYPE_TOKENS = ("CHAR", "VARCHAR", "TEXT", "STRING", "CLOB")


def accepted_semantic_type(semantic_record: dict[str, Any] | None) -> str | None:
    """Return the accepted ``type_id``, or ``None`` if not steward-accepted.

    A record only counts for 0b when it has been accepted (``accepted_at`` set) and it
    carries a real (non-``unresolved``) type_id.
    """
    if not semantic_record:
        return None
    if not semantic_record.get("accepted_at"):
        return None
    type_id = semantic_record.get("type_id")
    if not type_id or type_id == "unresolved":
        return None
    return str(type_id)


def _is_key_role(col_dict: ColumnDict, tbl_dict: TableDict | None) -> bool:
    """True when the column has a declared/inferred PK or declared FK-source duty."""
    name = col_dict.get("name")
    if col_dict.get("is_primary_key") or col_dict.get("primary_key"):
        return True
    if col_dict.get("is_foreign_key") or col_dict.get("foreign_key"):
        return True
    tbl = tbl_dict or {}
    ipk = tbl.get("inferred_primary_key") or tbl.get("primary_key") or []
    if isinstance(ipk, str):
        ipk = [ipk]
    if name in ipk:
        return True
    for rel in tbl.get("inferred_relations", []) or []:
        if name in (rel.get("from_column"), rel.get("column")):
            return True
    return False


def _is_numeric_type(data_type: str) -> bool:
    return any(tok in data_type for tok in _NUMERIC_TYPE_TOKENS)


def _is_date_type(data_type: str) -> bool:
    return any(tok in data_type for tok in _DATE_TYPE_TOKENS)


def _is_string_type(data_type: str) -> bool:
    return any(tok in data_type for tok in _STRING_TYPE_TOKENS)


def detect_archetype(
    col_dict: ColumnDict,
    tbl_dict: TableDict | None,
    semantic_record: dict[str, Any] | None,
    config: DQScoringConfig,
) -> tuple[str, str]:
    """Return ``(archetype, reason)`` for *col_dict* under F1 precedence.

    *reason* names the rule that fired, for persistence as evidence (DQ §16.6).
    """
    det = config.archetype_detection or {}
    key_uniqueness_min = float(det.get("key_uniqueness_min", 0.995))
    key_min_rows = int(det.get("key_min_rows", 100))
    coded_max_distinct = int(det.get("coded_max_distinct", 50))
    pattern_confidence_min = float(det.get("pattern_confidence_min", 0.80))

    data_type = str(col_dict.get("data_type") or "").upper()

    # 0a — key duty is real regardless of meaning.
    if _is_key_role(col_dict, tbl_dict):
        return "key_like", "0a: declared/inferred key role"

    # 0b — a steward-accepted semantic type overrides heuristics.
    type_id = accepted_semantic_type(semantic_record)
    if type_id:
        mapped = (config.semantic_type_archetype_map or {}).get(type_id)
        if mapped:
            return mapped, f"0b: accepted semantic type '{type_id}' -> {mapped}"

    # 1 — key_like heuristic (uniqueness on a large-enough table).
    uniqueness_pct = col_dict.get("uniqueness_pct")
    row_count = col_dict.get("row_count") or 0
    if (
        uniqueness_pct is not None
        and float(uniqueness_pct) >= key_uniqueness_min
        and int(row_count) >= key_min_rows
    ):
        return "key_like", f"1: uniqueness {uniqueness_pct} >= {key_uniqueness_min}"

    # 2 — coded (low cardinality).
    distinct_count = col_dict.get("distinct_count")
    if distinct_count is not None and int(distinct_count) <= coded_max_distinct:
        return "coded", f"2: distinct_count {distinct_count} <= {coded_max_distinct}"

    # 3 — date (declared or inferred).
    if _is_date_type(data_type) or col_dict.get("inferred_pattern") == "DATE":
        return "date", "3: declared/inferred date"

    # 4 — numeric (declared numeric type).
    if _is_numeric_type(data_type):
        return "numeric", "4: declared numeric type"

    # 5 — text (string with a reliable validity yardstick).
    pattern = col_dict.get("inferred_pattern")
    pattern_confidence = col_dict.get("pattern_confidence")
    if (
        _is_string_type(data_type)
        and pattern
        and pattern != "DATE"
        and pattern_confidence is not None
        and float(pattern_confidence) >= pattern_confidence_min
    ):
        return "text", f"5: pattern {pattern} confidence {pattern_confidence}"

    # 6 — free_text default (no reliable yardstick).
    return "free_text", "6: default (no reliable pattern/type check)"
