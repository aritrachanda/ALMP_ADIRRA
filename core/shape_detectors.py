"""Pure numeric/structural shape detectors — shared signal library.

Consumed by BOTH the semantic resolver (candidate initiation) and DQ scoring
(Consistency/Plausibility evidence). Detectors are stateless: sample values in,
a small evidence dict out. No I/O, no imports from the resolver or the store —
mirrors the pattern already established in ``core.type_validators``.

Each detector prefers profiler-persisted stats already present on
``column_meta`` (e.g. ``decimal_scale_distribution``, ``uniqueness_pct``,
``numeric_stddev``, ``min_value``/``max_value``) and falls back to computing
from ``values`` only when the stat is absent.

Return shape (all detectors except ``currency_sibling``, which is a table-level
boolean helper)::

    {"signal": str, "fired": bool, "share": float | None, "detail": str}
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

ColumnMeta = dict[str, Any]


def _clean_numeric(values: Iterable[object] | None) -> list[float]:
    """Coerce an iterable of raw sample values to floats, dropping unparsable/blank entries."""
    cleaned: list[float] = []
    for value in values or []:
        if value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        try:
            cleaned.append(float(text))
        except (ValueError, TypeError):
            continue
    return cleaned


def _decimal_places(value: object) -> int | None:
    """Return the number of digits after the decimal point, or ``None`` if unparsable."""
    text = str(value).strip() if value is not None else ""
    if text == "":
        return None
    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
    exponent = dec.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def decimal_scale_consistent(
    values: Sequence[object] | Iterable[object] | None,
    meta: ColumnMeta | None = None,
    *,
    min_share: float = 0.90,
    scales: tuple[int, ...] = (2, 3, 4),
) -> dict[str, Any]:
    """Detect whether values consistently use one decimal scale from *scales*.

    Prefers the profiler-persisted ``decimal_scale_distribution`` (a
    ``{scale: share}`` dict) on *meta*; falls back to computing scales
    directly from *values* when that stat is absent.
    """
    meta = meta or {}
    distribution = meta.get("decimal_scale_distribution")
    if isinstance(distribution, dict) and distribution:
        shares = {int(k): float(v) for k, v in distribution.items()}
    else:
        places = [p for p in (_decimal_places(v) for v in (values or [])) if p is not None]
        if not places:
            return {"signal": "decimal_scale_consistent", "fired": False, "share": None,
                     "detail": "no parseable numeric values"}
        counts: dict[int, int] = {}
        for p in places:
            counts[p] = counts.get(p, 0) + 1
        total = len(places)
        shares = {scale: count / total for scale, count in counts.items()}

    candidate_shares = {scale: share for scale, share in shares.items() if scale in scales}
    if not candidate_shares:
        return {"signal": "decimal_scale_consistent", "fired": False, "share": 0.0,
                 "detail": f"no observed values at scales {scales}"}
    best_scale, best_share = max(candidate_shares.items(), key=lambda kv: kv[1])
    fired = best_share >= min_share
    return {
        "signal": "decimal_scale_consistent",
        "fired": fired,
        "share": round(best_share, 4),
        "detail": f"{round(best_share * 100, 1)}% of values at scale {best_scale}",
    }


def declared_scale(meta: ColumnMeta | None = None, *, min_scale: int = 2) -> dict[str, Any]:
    """Detect a declared decimal scale/precision on the column's data type.

    Reads ``meta['declared_scale']`` (falls back to ``meta['scale']``) — a
    schema-declared fact (e.g. DECIMAL(18,2) declares scale 2), never
    recomputed from sample values.
    """
    meta = meta or {}
    scale = meta.get("declared_scale", meta.get("scale"))
    if scale is None:
        return {"signal": "declared_scale", "fired": False, "share": None,
                 "detail": "no declared scale on column metadata"}
    try:
        scale = int(scale)
    except (TypeError, ValueError):
        return {"signal": "declared_scale", "fired": False, "share": None,
                 "detail": f"unparseable declared scale: {scale!r}"}
    fired = scale >= min_scale
    return {
        "signal": "declared_scale",
        "fired": fired,
        "share": None,
        "detail": f"declared scale {scale}",
    }


def bounded_range(
    values: Sequence[object] | Iterable[object] | None,
    meta: ColumnMeta | None = None,
    *,
    ranges: tuple[tuple[float, float], ...] = ((-1, 1), (0, 100)),
    min_share: float = 0.95,
) -> dict[str, Any]:
    """Detect whether values fall within one of a set of plausible bounded ranges.

    Falls back to the profiler-persisted ``min_value``/``max_value`` for a
    cheap accept when no sample values are supplied but the observed range
    already fits within a candidate range.
    """
    meta = meta or {}
    cleaned = _clean_numeric(values)
    if not cleaned:
        min_v, max_v = meta.get("min_value"), meta.get("max_value")
        if min_v is not None and max_v is not None:
            try:
                min_v, max_v = float(min_v), float(max_v)
            except (TypeError, ValueError):
                min_v = max_v = None
            if min_v is not None:
                for lo, hi in ranges:
                    if lo <= min_v and max_v <= hi:
                        return {"signal": "bounded_range", "fired": True, "share": 1.0,
                                 "detail": f"profiler range [{min_v}, {max_v}] within [{lo}, {hi}]"}
        return {"signal": "bounded_range", "fired": False, "share": None,
                 "detail": "no parseable numeric values"}

    best_share, best_range = 0.0, None
    for lo, hi in ranges:
        share = sum(1 for v in cleaned if lo <= v <= hi) / len(cleaned)
        if share > best_share:
            best_share, best_range = share, (lo, hi)
    fired = best_share >= min_share
    return {
        "signal": "bounded_range",
        "fired": fired,
        "share": round(best_share, 4),
        "detail": f"{round(best_share * 100, 1)}% of values within {best_range}" if best_range else "no matching range",
    }


def sign_distribution(
    values: Sequence[object] | Iterable[object] | None,
    meta: ColumnMeta | None = None,
) -> dict[str, Any]:
    """Report the share of positive/negative/zero values.

    Descriptive, not a pass/fail gate — ``fired`` is True whenever at least
    one sample was parseable as numeric.
    """
    cleaned = _clean_numeric(values)
    if not cleaned:
        return {"signal": "sign_distribution", "fired": False, "share": None,
                 "detail": "no parseable numeric values"}
    total = len(cleaned)
    positive = sum(1 for v in cleaned if v > 0) / total
    negative = sum(1 for v in cleaned if v < 0) / total
    zero = sum(1 for v in cleaned if v == 0) / total
    return {
        "signal": "sign_distribution",
        "fired": True,
        "share": round(max(positive, negative, zero), 4),
        "detail": f"positive={round(positive, 4)} negative={round(negative, 4)} zero={round(zero, 4)}",
    }


def year_like_range(
    values: Sequence[object] | Iterable[object] | None,
    meta: ColumnMeta | None = None,
    *,
    min_share: float = 0.90,
) -> dict[str, Any]:
    """Detect integers clustered in a plausible calendar-year range (1900-2100)."""
    cleaned = _clean_numeric(values)
    if not cleaned:
        return {"signal": "year_like_range", "fired": False, "share": None,
                 "detail": "no parseable numeric values"}
    integral = [v for v in cleaned if float(v).is_integer()]
    if not integral:
        return {"signal": "year_like_range", "fired": False, "share": 0.0,
                 "detail": "no integer-valued samples"}
    in_range = sum(1 for v in integral if 1900 <= v <= 2100)
    share = in_range / len(cleaned)
    fired = share >= min_share
    return {
        "signal": "year_like_range",
        "fired": fired,
        "share": round(share, 4),
        "detail": f"{round(share * 100, 1)}% of values are integers in [1900, 2100]",
    }


def unique_ratio(meta: ColumnMeta | None = None, *, gte: float = 0.95) -> dict[str, Any]:
    """Detect near-unique columns using the profiler's persisted ``uniqueness_pct``."""
    meta = meta or {}
    ratio = meta.get("uniqueness_pct")
    if ratio is None:
        distinct, row_count = meta.get("distinct_count"), meta.get("row_count")
        if distinct is not None and row_count:
            ratio = distinct / row_count
    if ratio is None:
        return {"signal": "unique_ratio", "fired": False, "share": None,
                 "detail": "no uniqueness data available"}
    ratio = float(ratio)
    return {
        "signal": "unique_ratio",
        "fired": ratio >= gte,
        "share": round(ratio, 4),
        "detail": f"uniqueness {round(ratio * 100, 1)}%",
    }


def low_cardinality_enum(
    meta: ColumnMeta | None = None,
    *,
    max_distinct: int = 10,
    max_ratio: float = 0.02,
) -> dict[str, Any]:
    """Detect low-cardinality enum-like columns from persisted distinct/row counts."""
    meta = meta or {}
    distinct = meta.get("distinct_count")
    if distinct is None:
        return {"signal": "low_cardinality_enum", "fired": False, "share": None,
                 "detail": "no distinct_count available"}
    row_count = meta.get("row_count")
    ratio = (distinct / row_count) if row_count else None
    fired = distinct <= max_distinct or (ratio is not None and ratio <= max_ratio)
    detail = f"distinct_count={distinct}" + (f", ratio={round(ratio, 4)}" if ratio is not None else "")
    return {
        "signal": "low_cardinality_enum",
        "fired": fired,
        "share": round(ratio, 4) if ratio is not None else None,
        "detail": detail,
    }


_CURRENCY_NAME_TOKENS = {"currency", "ccy", "curr"}


def currency_sibling(table_dict: dict[str, Any] | None) -> bool:
    """Return True if any sibling column in *table_dict* looks like a currency column.

    Simple, documented heuristic: an ISO-currency-like ``inferred_pattern``
    or a currency-ish name token (currency, ccy, curr).
    """
    for column in (table_dict or {}).get("columns", []) or []:
        pattern = str(column.get("inferred_pattern") or "").upper()
        if "CURRENCY" in pattern:
            return True
        name = str(column.get("name") or "").lower()
        tokens = set(name.replace("-", "_").split("_"))
        if tokens & _CURRENCY_NAME_TOKENS:
            return True
    return False
