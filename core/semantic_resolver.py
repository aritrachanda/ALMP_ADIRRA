"""Deterministic semantic-type resolver.

The resolver reads existing catalog/profile facts only. It does not re-profile or
write source data. The optional LLM layer is added later and must remain gated.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from core.semantic_type_store import SemanticTypeStore
from core.semantic_types import SemanticVocabulary, SemanticTypeEntry, load_semantic_vocabulary
from core.type_validators import run_validator, run_validator_detail
from core import shape_detectors

# U5b: bumped 6 → 7 when learned-pattern activation shipped. Approving a pattern
# writes it into governance/learned_patterns.yaml, which makes
# _effective_name_tokens actually extend a type's detectors — a scoring-behaviour
# change. The bump marks every cached `proposed` record stale so it re-scores on
# next resolve (confirmed/rejected stay sticky via the fingerprint path).
# SD-R1: bumped 7 → 8 with the one-field-of-truth fix. `_record_from_signal` now
# derives the top-level `tier` from `score_breakdown.tier` when a shortcut signal
# omits it, so cached `proposed` records that were persisted with a wrong `tier=0`
# (distribution-first / varchar-date paths) re-resolve and heal. No confidence
# value changes — only the stored `tier` becomes consistent with score_breakdown.
# ST-NS: bumped 8 → 9 with the Natural ID / Surrogate ID identifier split. The
# generic `identifier` type became `natural_identifier` + `surrogate_identifier`
# (default surrogate), the `identifier` category split into `natural_id` /
# `surrogate_id` domains, and legacy `identifier` records alias to surrogate. The
# bump re-scores cached `proposed` records under the new domains; confirmed/rejected
# stay sticky (their legacy domain_role/type_id are normalised at read time).
# SD-R4: bumped 9 → 10 removing the governance-signal confidence nudge (confirmed
# glossary link / approved definition, +0.05 each, capped). Measured 2026-08-12:
# changed 0 of 54 governance-carrying columns' outcome — the interpretation-set
# submit gate already requires the semantic type to be Accepted BEFORE a
# definition/glossary link can reach `approved`/`confirmed`, so the nudge could
# never actually influence the decision it fired after. Removing it makes the
# resolver fully deterministic on data + naming, and (together with dropping the
# two governance fields from the fingerprint, same change) ends the fingerprint
# churn those two fields caused. This bump re-scores every cached machine-state
# record once so stored evidence/confidence matches the new, nudge-free scoring;
# confirmed/rejected stay sticky as always.
RESOLVER_VERSION = "10"
_VALIDATOR_SAMPLE_LIMIT = 1000  # matches profiler._VALIDATOR_SAMPLE_LIMIT for evidence messages

#: Sentinel for resolve_column's `existing` param -- distinguishes "caller didn't pass a
#: pre-fetched record, go fetch it yourself" (default, every pre-existing caller) from a
#: real `existing=None` (caller pre-fetched and genuinely found no prior record).
_NOT_FETCHED = object()

# Types whose validator binding is only honoured under evidence widening (U1a).
# With the flag off these fall back to their pre-U1a (name-token) path, keeping
# resolver output byte-identical. datetime gains a timestamp_parse validator that
# must not fire until widening is enabled for the source.
_WIDEN_ONLY_VALIDATOR_TYPES = {"datetime"}

_VOCABULARY_CACHE: SemanticVocabulary | None = None

_ROOT = Path(__file__).resolve().parent.parent


def _get_vocabulary() -> SemanticVocabulary:
    global _VOCABULARY_CACHE
    if _VOCABULARY_CACHE is None:
        _VOCABULARY_CACHE = load_semantic_vocabulary()
    return _VOCABULARY_CACHE


def invalidate_vocabulary_cache() -> None:
    """Force the next resolve call to reload the vocabulary from disk."""
    global _VOCABULARY_CACHE
    _VOCABULARY_CACHE = None


# Invalidate at import time so server restart picks up vocabulary changes.
invalidate_vocabulary_cache()
DEFAULT_HIGH_THRESHOLD = 0.85
DEFAULT_FLOOR_THRESHOLD = 0.60

# Plain-language labels for the confidence tier — surfaced in the score breakdown.
_TIER_LABELS = {0: "None", 1: "Validated", 2: "Structural", 3: "Suggested"}


def _build_breakdown(top: dict[str, Any] | None, cap: float) -> dict[str, Any] | None:
    """Itemise how a candidate's confidence was reached: tier base + capped adjustments.

    Returns ``None`` when there is no scored candidate (pure unresolved). The shape is
    consumed by the Mapping Type tab to render a transparent scoring waterfall.
    """
    if not top:
        return None
    base = float(top.get("base", top.get("score", 0.0)) or 0.0)
    adjustments = list(top.get("adjustments", []) or [])
    tier = int(top.get("tier", 0) or 0)
    raw_total = sum(float(a.get("points", 0.0) or 0.0) for a in adjustments)
    applied = round(min(cap, raw_total), 4) if adjustments else 0.0
    return {
        "base": round(base, 4),
        "tier": tier,
        "tier_label": _TIER_LABELS.get(tier, "None"),
        "adjustments": adjustments,
        "adjustment_total": applied,
        "adjustment_capped": raw_total > cap,
        "adjustment_cap": cap,
        "final": float(top.get("score", round(base + applied, 4))),
    }


_CATEGORY_TO_DOMAIN_ROLE = {
    "natural_id": "natural_id",
    "surrogate_id": "surrogate_id",
    "monetary": "measure",
    "quantity": "measure",
    "rate": "rate",
    "temporal": "temporal",
    "code": "code",
    "name": "name",
    "address": "address",
    "text": "text",
    "technical": "technical",
    # Legacy categories (backward compat)
    "identifier": "surrogate_id",   # pre-split generic identifier defaults to surrogate
    "textual": "text",
    "classification": "code",
}

# Legacy type_id aliases — stored/confirmed records that still carry a pre-rename
# type_id map to the current id so vocabulary lookups and scope/pii derivation keep
# working. The pre-split generic 'identifier' and 'surrogate_identifier' land on the
# generic surrogate (see LOCKED DECISION: default surrogate); the validator-backed
# natural formats gained a natural_<format> id.
_LEGACY_TYPE_ALIASES = {
    "identifier": "surrogate_systemid",
    "surrogate_identifier": "surrogate_systemid",
    "natural_identifier": "natural_key",
    "iban": "natural_iban",
    "bic": "natural_bic",
    "lei": "natural_lei",
    "isin": "natural_isin",
    "henkilotunnus": "natural_henkilotunnus",
    "y_tunnus": "natural_yritystunnus",
    # 2026-08-20 rename: old ids kept so already-persisted records normalise forward.
    "natural_htun": "natural_henkilotunnus",
    "natural_ytun": "natural_yritystunnus",
}


def normalise_type_id(type_id: str | None) -> str:
    """Map a stored/legacy type_id to its current vocabulary id (identity if none).

    Confirmed records are sticky and may still carry a pre-rename type_id; callers
    that surface the type to the UI use this so a legacy 'identifier' displays as
    its current 'surrogate_systemid' rather than a stale label.
    """
    if not type_id:
        return "unresolved"
    return _LEGACY_TYPE_ALIASES.get(type_id, type_id)


def domain_role_for_type(type_id: str | None) -> str | None:
    """Return the canonical domain role for a type_id from the vocabulary.

    Used to keep a confirmed/overridden type_id and its domain_role in sync — an
    override that changes the type must not leave a stale domain behind (e.g. a
    'natural_key' must land on 'natural_id', never a leftover 'surrogate_id').
    Returns ``None`` when the type is unknown/unresolved so callers can fall back.
    """
    if not type_id or type_id == "unresolved":
        return None
    tid = _LEGACY_TYPE_ALIASES.get(type_id, type_id)
    entry = _get_vocabulary().get(tid)
    if entry is None:
        return None
    return _CATEGORY_TO_DOMAIN_ROLE.get(entry.category, "unresolved")

_DOMAIN_ROLE_TO_LEGACY_BUCKET = {
    "key": "identifier",
    "natural_id": "identifier",
    "surrogate_id": "identifier",
    "identifier": "identifier",
    "code": "coded",
    "temporal": "date",
    "measure": "monetary",
    "rate": "monetary",
    "name": "other",
    "address": "other",
    "text": "other",
    "dimension": "other",
    "descriptive": "other",
    "technical": "other",
    "unresolved": "other",
}

# How scope is derived from scope_source on the vocabulary entry
_SCOPE_SOURCE_TO_SCOPE = {
    "global_standard": "global",
    "national_standard": "regional",
    "distribution": "internal",
    "default": "internal",
}

_FINGERPRINT_COL_FIELDS = (
    "name", "data_type", "row_count", "null_pct", "distinct_count", "uniqueness_pct",
    "sample_values", "inferred_pattern", "min_value", "max_value",
    "validator_pass_rates",
)
_FINGERPRINT_TABLE_FIELDS = ("schema_name", "table_name", "row_count", "primary_key", "inferred_primary_key")

_ENTITY_PROFILES = {
    "Account": {
        "table_tokens": {"account", "accounts", "acct"},
        "column_tokens": {"account", "account_id", "balance", "currency", "status", "account_type"},
        "min_matches": 3,
    },
    "Counterparty": {
        "table_tokens": {"counterparty", "counterparties", "cpty", "party", "customer", "client"},
        "column_tokens": {"counterparty", "counterparty_id", "cpty", "party", "customer", "name", "lei", "country", "sector"},
        "min_matches": 3,
    },
}


DEFAULT_HIGH_THRESHOLD = 0.85
DEFAULT_FLOOR_THRESHOLD = 0.60
DEFAULT_SUGGESTED_THRESHOLD = 0.45


@dataclass(frozen=True)
class ResolverConfig:
    high_threshold: float = DEFAULT_HIGH_THRESHOLD
    floor_threshold: float = DEFAULT_FLOOR_THRESHOLD
    suggested_threshold: float = DEFAULT_SUGGESTED_THRESHOLD
    tier_validated: float = 0.90
    tier_structural: float = 0.70
    tier_suggested: float = 0.45
    adjustment_cap: float = 0.08
    validator_decisive: float = 0.95
    validator_confirm_floor: float = 0.70
    # Per-source evidence widening (U1a) — default OFF; with OFF, resolver output
    # is byte-identical to pre-U1a. Flipped per source in U1b.
    evidence_widening_default: bool = False
    evidence_widening_sources: Mapping[str, bool] = field(default_factory=dict)

    @classmethod
    def from_project(cls, project: dict[str, Any] | None = None) -> "ResolverConfig":
        cfg = (project or {}).get("semantic_type_resolver", {})
        widening = cfg.get("evidence_widening", {}) or {}
        return cls(
            high_threshold=float(cfg.get("high_threshold", DEFAULT_HIGH_THRESHOLD)),
            floor_threshold=float(cfg.get("floor_threshold", DEFAULT_FLOOR_THRESHOLD)),
            suggested_threshold=float(cfg.get("suggested_threshold", DEFAULT_SUGGESTED_THRESHOLD)),
            tier_validated=float(cfg.get("tier_validated", 0.90)),
            tier_structural=float(cfg.get("tier_structural", 0.70)),
            tier_suggested=float(cfg.get("tier_suggested", 0.45)),
            adjustment_cap=float(cfg.get("adjustment_cap", 0.08)),
            validator_decisive=float(cfg.get("validator_decisive", 0.95)),
            validator_confirm_floor=float(cfg.get("validator_confirm_floor", 0.70)),
            evidence_widening_default=bool(widening.get("default", False)),
            evidence_widening_sources=dict(widening.get("sources", {}) or {}),
        )

    def evidence_widening_for(self, source: str | None) -> bool:
        """Return whether evidence widening is enabled for *source* (per-source override, else default)."""
        if source and source in self.evidence_widening_sources:
            return bool(self.evidence_widening_sources[source])
        return self.evidence_widening_default


def domain_role_to_legacy_bucket(domain_role: str | None) -> str:
    return _DOMAIN_ROLE_TO_LEGACY_BUCKET.get(domain_role or "unresolved", "other")


def get_vocabulary_structure() -> dict[str, Any]:
    """Return the governed vocabulary as a UI-ready structure for dropdowns."""
    vocab = _get_vocabulary()
    roles = [
        {"id": "natural_id", "label": "Natural ID"},
        {"id": "surrogate_id", "label": "Surrogate ID"},
        {"id": "code", "label": "Code"},
        {"id": "rate", "label": "Rate"},
        {"id": "measure", "label": "Measure"},
        {"id": "temporal", "label": "Temporal"},
        {"id": "name", "label": "Name"},
        {"id": "address", "label": "Address"},
        {"id": "text", "label": "Text"},
        {"id": "technical", "label": "Technical"},
    ]
    types_by_role: dict[str, list[dict[str, str]]] = {}
    for entry in vocab.entries:
        dr = _CATEGORY_TO_DOMAIN_ROLE.get(entry.category, "text")
        types_by_role.setdefault(dr, [])
        types_by_role[dr].append({"id": entry.id, "label": entry.label or entry.id})
    return {
        "roles": roles,
        "types_by_role": types_by_role,
        "scopes": [
            {"id": "global", "label": "Global"},
            {"id": "regional", "label": "Regional"},
            {"id": "internal", "label": "Internal"},
        ],
    }


def _fingerprint_column_payload(column: dict[str, Any]) -> dict[str, Any]:
    """Build the column side of the fingerprint payload.

    ``sample_values`` is hashed as a sorted set, not the raw list order, so a
    profiler/storage change that returns the same values in a different order
    (or a different arbitrary subset of an unbounded-cardinality distinct query)
    can never by itself flip the fingerprint — see SD-R4 for the bug this closes.
    """
    payload = {field: column.get(field) for field in _FINGERPRINT_COL_FIELDS}
    samples = payload.get("sample_values")
    if isinstance(samples, list):
        payload["sample_values"] = sorted(str(v) for v in samples)
    return payload


def column_fingerprint(column: dict[str, Any], table: dict[str, Any] | None = None) -> str:
    payload = {
        "column": _fingerprint_column_payload(column),
        "table": {field: (table or {}).get(field) for field in _FINGERPRINT_TABLE_FIELDS},
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


ColumnProgressStatus = Literal["recheck", "first_time", "cache_hit"]


def _column_progress_status(
    existing: dict[str, Any] | None,
    fingerprint: str,
) -> ColumnProgressStatus:
    """Read-only classification of an ALREADY-FETCHED record, WITHOUT resolving or
    persisting anything — used only to report honest progress (never to decide the real
    resolve; ``resolve_column``'s own cache-hit check runs the identical comparison, reusing
    the SAME fetched record rather than reading it again — a column used to pay for this
    lookup twice, found live 2026-08-14 once semantic types moved off an in-memory YAML dict).
    Returns "recheck" only when this column was resolved before AND its stored fingerprint
    no longer matches — a genuine re-check triggered by the source data profile changing.
    Returns "first_time" when the column has never been resolved before (no store record at
    all). Returns "cache_hit" for a fast cache hit (resolved before, fingerprint unchanged).
    """
    if not existing:
        return "first_time"
    if existing.get("fingerprint") != fingerprint:
        return "recheck"
    return "cache_hit"


def _conflict_rationale(record: dict[str, Any], target: str) -> str:
    type_id = record.get("type_id") or "candidate type"
    for evidence in record.get("evidence", []):
        if evidence.get("kind") == "validator" and evidence.get("weight") == "refutes":
            return f"Name or pattern suggests {type_id} for '{target}', but sampled values fail its validator."
    return f"Evidence disagrees on the semantic type for '{target}'."


def conflict_finding(record: dict[str, Any], *, column: str | None = None) -> dict[str, Any]:
    target = column or str(record.get("key", "")).split("|")[-1]
    return {
        "scope": "column",
        "target": target,
        "severity": "attention",
        "category": "validity",
        "title": "Type/value conflict",
        "rationale": _conflict_rationale(record, target),
        "evidence": {"semantic_type": record.get("type_id"), "evidence": record.get("evidence", [])},
        "source": "rule",
    }


def _tokens(name: str) -> set[str]:
    parts = re.split(r"[^a-zA-Z0-9]+", name.lower())
    tokens = {part for part in parts if part}
    compact = name.lower()
    if compact:
        tokens.add(compact)
    return tokens


def _normalise_primitive(data_type: str | None) -> str:
    dtype = (data_type or "").upper()
    if any(marker in dtype for marker in ("DATE", "TIME")):
        return "date"
    # Integers
    if any(marker in dtype for marker in ("TINYINT", "SMALLINT", "BIGINT", "INT")):
        return "integer"
    # Decimals/floats
    if any(marker in dtype for marker in ("DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL")):
        return "decimal"
    if any(marker in dtype for marker in ("BOOL", "BIT")):
        return "boolean"
    return "string"


def _samples(column: dict[str, Any]) -> list[Any]:
    values = column.get("sample_values") or []
    return values if isinstance(values, list) else []


def _match_name(name_tokens: set[str], detector_tokens: Iterable[str]) -> tuple[bool, str | None]:
    lowered = [token.lower() for token in detector_tokens]
    compact_name = "_".join(sorted(name_tokens))
    for token in lowered:
        clean = token.strip().lower()
        if not clean:
            continue
        if clean in name_tokens:
            return True, clean
        if clean.startswith("_") and any(name.endswith(clean) for name in name_tokens):
            return True, clean
        if clean in compact_name:
            return True, clean
    return False, None


def _run_shape_detector(
    name: str,
    params: Any,
    *,
    values: list[Any],
    meta: dict[str, Any],
    table_dict: dict[str, Any],
) -> dict[str, Any] | None:
    """Evaluate one shape detector by name, translating vocab YAML params to kwargs.

    Returns the detector's ``{signal, fired, share, detail}`` dict, or ``None`` for
    an unknown detector name. ``currency_sibling`` (a bare bool helper) is wrapped
    into the same dict shape here so callers can treat every entry uniformly.
    """
    params = params if isinstance(params, dict) else {}
    if name == "decimal_scale_consistent":
        kwargs: dict[str, Any] = {}
        if "min_share" in params:
            kwargs["min_share"] = float(params["min_share"])
        if "scales" in params:
            kwargs["scales"] = tuple(int(s) for s in params["scales"])
        return shape_detectors.decimal_scale_consistent(values, meta, **kwargs)
    if name == "declared_scale":
        kwargs = {}
        if "min" in params:
            kwargs["min_scale"] = int(params["min"])
        elif "min_scale" in params:
            kwargs["min_scale"] = int(params["min_scale"])
        return shape_detectors.declared_scale(meta, **kwargs)
    if name == "bounded_range":
        kwargs = {}
        if "ranges" in params:
            kwargs["ranges"] = tuple((float(lo), float(hi)) for lo, hi in params["ranges"])
        if "min_share" in params:
            kwargs["min_share"] = float(params["min_share"])
        return shape_detectors.bounded_range(values, meta, **kwargs)
    if name == "unique_ratio":
        kwargs = {}
        if "gte" in params:
            kwargs["gte"] = float(params["gte"])
        return shape_detectors.unique_ratio(meta, **kwargs)
    if name == "year_like_range":
        return shape_detectors.year_like_range(values, meta)
    if name == "low_cardinality_enum":
        kwargs = {}
        if "max_distinct" in params:
            kwargs["max_distinct"] = int(params["max_distinct"])
        if "max_ratio" in params:
            kwargs["max_ratio"] = float(params["max_ratio"])
        return shape_detectors.low_cardinality_enum(meta, **kwargs)
    if name == "sign_distribution":
        return shape_detectors.sign_distribution(values)
    if name == "currency_sibling":
        fired = shape_detectors.currency_sibling(table_dict)
        return {
            "signal": "currency_sibling",
            "fired": bool(fired),
            "share": None,
            "detail": "a currency-coded sibling column is present" if fired else "no currency sibling",
        }
    return None


def _eval_shape_list(
    spec_list: Any,
    *,
    values: list[Any],
    meta: dict[str, Any],
    table_dict: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(name, result)`` for each shape-detector spec entry that fired."""
    fired: list[tuple[str, dict[str, Any]]] = []
    for item in spec_list or []:
        if not isinstance(item, dict) or len(item) != 1:
            continue
        (detector_name, params), = item.items()
        result = _run_shape_detector(
            str(detector_name), params, values=values, meta=meta, table_dict=table_dict
        )
        if result and result.get("fired"):
            fired.append((str(detector_name), result))
    return fired


def _distribution_first_signal(
    column: dict[str, Any],
    table_facts: dict[str, Any],
    *,
    ref_code_cardinality_max: int = 50,
    ref_code_value_length_max: int = 40,
    identifier_uniqueness_min: float = 0.98,
) -> dict[str, Any] | None:
    """Return a high-confidence signal based purely on distribution — no name match required.

    This is the primary fix for columns like accounting_standard_code, Source_System,
    GL account numbers, etc. that score 0.16 under the per-candidate loop because they
    have no name token match against any vocabulary type.

    Only one path is implemented today:
    - reference_code: distinct <= threshold AND all samples are short strings
      (constant or low-cardinality enumerable). A constant column (distinct=1) is also
      caught here — it's definitionally a reference code.

    High-uniqueness identifiers are NOT handled here — they are resolved by the T2
    distribution branch in the main ``_score_column`` loop (which requires PK
    membership). The ``identifier_uniqueness_min`` parameter is retained for a
    possible future path but is currently unused.
    """
    distinct = column.get("distinct_count") or 0
    row_count = column.get("row_count") or table_facts.get("row_count") or 0
    null_pct = column.get("null_pct") or 0.0
    dtype = (column.get("data_type") or "").upper()

    if not row_count:
        return None

    # Skip pure numeric types — they're handled by monetary/rate/date paths
    is_numeric = any(marker in dtype for marker in ("INT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL"))
    is_date = any(marker in dtype for marker in ("DATE", "TIME"))
    if is_numeric or is_date:
        return None

    # PATH 1 — reference_code: low cardinality + short values + genuinely low cardinality ratio
    if 0 < distinct <= ref_code_cardinality_max:
        cardinality_ratio = distinct / row_count
        # Require genuinely low cardinality ratio. A column where ≥15% of rows are
        # distinct is an identifier, not a code — catches small test tables where
        # 3 distinct / 3 rows = 100% looks "low cardinality" on the count alone.
        if cardinality_ratio > 0.15:
            return None
        samples_local = _samples(column)
        cleaned = [str(v).strip() for v in samples_local if v is not None and str(v).strip()]
        if cleaned and all(len(v) <= ref_code_value_length_max for v in cleaned):
            confidence = min(0.93, 0.82 + (1.0 - cardinality_ratio) * 0.11)
            return {
                "type_id": "reference_code",
                "domain_role": "code",
                "confidence": round(confidence, 4),
                "score_breakdown": {
                    "base": round(confidence, 4),
                    "tier": 2,
                    "tier_label": "Structural",
                    "adjustments": [],
                    "adjustment_total": 0.0,
                    "adjustment_capped": False,
                    "adjustment_cap": 0.08,
                    "final": round(confidence, 4),
                },
                "evidence": [
                    {
                        "kind": "distribution",
                        "signal": f"{distinct} distinct value(s) — low-cardinality code/enumeration",
                        "weight": "decisive",
                    }
                ],
            }

    return None


# ── Value-structure signals (ST-NS) ─────────────────────────────────────────
# Deterministic structure metrics over a column's sample values, used to (a)
# tell an identifier-shaped column from free text and (b) lean surrogate vs
# natural, for columns with no known format validator and no identifier name
# token (e.g. `SYS236176M`). Low-mid confidence — steward-reviewable, never a
# hard override.

def _structural_mask(value: str) -> str:
    """Map a value to a structural mask: A=letter, 9=digit, literal for others."""
    out: list[str] = []
    for ch in value:
        if ch.isalpha():
            out.append("A")
        elif ch.isdigit():
            out.append("9")
        else:
            out.append(ch)
    return "".join(out)


def _leading_alpha(value: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out)


def _value_shape_metrics(column: dict[str, Any]) -> dict[str, Any] | None:
    """Structure metrics from a column's non-null string samples, or None when
    there are too few to judge (< 3)."""
    cleaned = [str(v).strip() for v in _samples(column) if v is not None and str(v).strip()]
    if len(cleaned) < 3:
        return None
    lengths = [len(v) for v in cleaned]
    mean_len = sum(lengths) / len(lengths)
    std_len = (sum((l - mean_len) ** 2 for l in lengths) / len(lengths)) ** 0.5
    length_cv = (std_len / mean_len) if mean_len else 1.0

    masks = [_structural_mask(v) for v in cleaned]
    mask_coverage = max(masks.count(m) for m in set(masks)) / len(masks)

    has_ws = any(" " in v for v in cleaned)
    alpha_only = sum(1 for v in cleaned
                     if v.replace(" ", "").replace("-", "").replace("'", "").replace(".", "").isalpha())
    alpha_ratio = alpha_only / len(cleaned)
    digit_ratio = sum(1 for v in cleaned if any(c.isdigit() for c in v)) / len(cleaned)

    leads = [_leading_alpha(v) for v in cleaned]
    prefix = ""
    if all(leads):
        shortest = min(leads, key=len)
        for i in range(len(shortest), 1, -1):
            cand = shortest[:i]
            if sum(1 for l in leads if l.startswith(cand)) / len(leads) >= 0.8:
                prefix = cand
                break

    nums: list[int] = []
    for v in cleaned:
        digits = "".join(c for c in v if c.isdigit())
        if digits:
            try:
                nums.append(int(digits))
            except ValueError:
                pass
    is_sequential = False
    if len(nums) >= 3:
        ordered = sorted(nums)
        diffs = [b - a for a, b in zip(ordered, ordered[1:])]
        if diffs and max(diffs) <= 5 and all(d >= 0 for d in diffs):
            is_sequential = True

    return {
        "n": len(cleaned),
        "length_cv": round(length_cv, 3),
        "mean_len": round(mean_len, 1),
        "mask_coverage": round(mask_coverage, 3),
        "has_whitespace": has_ws,
        "alpha_ratio": round(alpha_ratio, 3),
        "digit_ratio": round(digit_ratio, 3),
        "constant_affix": len(prefix) >= 2,
        "affix": prefix,
        "is_sequential": is_sequential,
    }


# Value-shape constants for surrogate format detection.
_UUID_DASHED_RE = re.compile(
    r'^(?:urn:uuid:)?\{?'
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    r'\}?$'
)
_HEX_RE = re.compile(r'^[0-9a-fA-F]+$')
_HASH_HEX_LENGTHS = {32, 40, 64, 128}  # MD5, SHA-1, SHA-256, SHA-512


def _surrogate_shape_signal(
    column: dict[str, Any],
    table_facts: dict[str, Any],
) -> dict[str, Any] | None:
    """Suggest a surrogate identifier for an identifier-SHAPED column that has
    no known format and no identifier name token, decided from value structure.

    Format-aware ordering:
      • Canonical dashed UUID values → defer (return None) so the main scorer's
        ``uuid_format`` validator lands ``surrogate_uuid`` at Tier 1.
      • Fixed-length hex values (32/40/64/128) with high uniqueness → suggest
        ``surrogate_hash`` at suggestion level (shape only — a hash can't be verified).
      • Otherwise (consistent mask/length, no whitespace, high uniqueness) →
        ``surrogate_systemid`` (default surrogate); sequential numeric core nudges up.
    """
    dtype = (column.get("data_type") or "").upper()
    if not any(marker in dtype for marker in ("CHAR", "TEXT", "STRING", "VARCHAR", "INT")):
        return None

    cleaned = [str(v).strip() for v in _samples(column) if v is not None and str(v).strip()]
    if cleaned:
        # UUID: distinctive dashed structure → let the validator claim Tier 1.
        if sum(1 for v in cleaned if _UUID_DASHED_RE.match(v)) / len(cleaned) >= 0.95:
            return None
        # Hash / opaque token: one fixed hex length across all samples + high uniqueness.
        lengths = {len(v) for v in cleaned}
        if (len(lengths) == 1 and next(iter(lengths)) in _HASH_HEX_LENGTHS
                and all(_HEX_RE.match(v) for v in cleaned)):
            distinct = column.get("distinct_count") or 0
            row_count = column.get("row_count") or table_facts.get("row_count") or 0
            non_null = row_count - (column.get("null_count") or 0)
            uniqueness = (distinct / non_null) if non_null else 0.0
            if uniqueness >= 0.9:
                length = next(iter(lengths))
                return {
                    "type_id": "surrogate_hash",
                    "domain_role": "surrogate_id",
                    "confidence": 0.5,
                    "score_breakdown": {
                        "base": 0.5, "tier": 3, "tier_label": "Suggested",
                        "adjustments": [], "adjustment_total": 0.0,
                        "adjustment_capped": False, "adjustment_cap": 0.08, "final": 0.5,
                    },
                    "evidence": [{
                        "kind": "shape",
                        "signal": (
                            f"fixed-length hex ({length} chars) with high uniqueness "
                            f"({int(uniqueness * 100)}%) — hash-like / opaque token "
                            "(shape only; a hash cannot be verified)"
                        ),
                        "weight": "moderate",
                    }],
                }

    metrics = _value_shape_metrics(column)
    if not metrics:
        return None
    # Free-text disqualifiers: whitespace or variable length.
    if metrics["has_whitespace"] or metrics["length_cv"] > 0.25:
        return None
    structured = metrics["mask_coverage"] >= 0.8 or metrics["constant_affix"]
    identifier_like = metrics["digit_ratio"] >= 0.8 or metrics["constant_affix"]
    if not (structured and identifier_like):
        return None
    distinct = column.get("distinct_count") or 0
    row_count = column.get("row_count") or table_facts.get("row_count") or 0
    non_null = row_count - (column.get("null_count") or 0)
    uniqueness = (distinct / non_null) if non_null else 0.0
    if uniqueness < 0.9:
        return None

    confidence = 0.5
    evidence = [{
        "kind": "shape",
        "signal": (
            f"consistent structure (mask coverage {int(metrics['mask_coverage'] * 100)}%"
            + (f", prefix '{metrics['affix']}'" if metrics["constant_affix"] else "")
            + f") + high uniqueness ({int(uniqueness * 100)}%), no whitespace — system-generated identifier shape"
        ),
        "weight": "moderate",
    }]
    if metrics["is_sequential"]:
        confidence = 0.55
        evidence.append({
            "kind": "shape",
            "signal": "sequential numeric core — surrogate serial pattern",
            "weight": "moderate",
        })
    return {
        "type_id": "surrogate_systemid",
        "domain_role": "surrogate_id",
        "confidence": confidence,
        "score_breakdown": {
            "base": confidence, "tier": 3, "tier_label": "Suggested",
            "adjustments": [], "adjustment_total": 0.0,
            "adjustment_capped": False, "adjustment_cap": 0.08, "final": confidence,
        },
        "evidence": evidence,
    }


def _regex_pass_rate(pattern: str | None, values: list[Any]) -> float | None:
    if not pattern or not values:
        return None
    compiled = re.compile(pattern)
    cleaned = [str(value).strip() for value in values if value is not None and str(value).strip()]
    if not cleaned:
        return None
    return sum(1 for value in cleaned if compiled.match(value)) / len(cleaned)


def _parse_numeric_date(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt)
    except ValueError:
        return None


def _numeric_varchar_date_signal(column: dict[str, Any]) -> dict[str, Any] | None:
    dtype = (column.get("data_type") or "").upper()
    if not any(marker in dtype for marker in ("CHAR", "TEXT", "STRING", "VARCHAR")):
        return None
    cleaned = [str(value).strip() for value in _samples(column) if value is not None and str(value).strip()]
    if not cleaned or not all(value.isdigit() and len(value) == 8 for value in cleaned):
        return None

    direction_passes: dict[str, int] = {"YYYYMMDD": 0, "DDMMYYYY": 0, "MMDDYYYY": 0}
    for value in cleaned:
        if _parse_numeric_date(value, "%Y%m%d"):
            direction_passes["YYYYMMDD"] += 1
        if _parse_numeric_date(value, "%d%m%Y"):
            direction_passes["DDMMYYYY"] += 1
        if _parse_numeric_date(value, "%m%d%Y"):
            direction_passes["MMDDYYYY"] += 1

    full_directions = [direction for direction, count in direction_passes.items() if count == len(cleaned)]
    if not full_directions:
        return None

    if any(int(value[:2]) > 12 for value in cleaned):
        forced = "DDMMYYYY"
    elif any(int(value[2:4]) > 12 for value in cleaned):
        forced = "MMDDYYYY"
    elif full_directions == ["YYYYMMDD"]:
        forced = "YYYYMMDD"
    elif len(full_directions) == 1:
        forced = full_directions[0]
    else:
        forced = "undecided"

    return {
        "type_id": "date",
        "domain_role": "temporal",
        "confidence": 0.90,
        "storage_mismatch": True,
        "format": forced,
        "score_breakdown": {
            "base": 0.90,
            "tier": 1,
            "tier_label": "Validated",
            "adjustments": [],
            "adjustment_total": 0.0,
            "adjustment_capped": False,
            "adjustment_cap": 0.08,
            "final": 0.90,
        },
        "evidence": [
            {
                "kind": "validator",
                "signal": "numeric VARCHAR values convert to dates",
                "weight": "decisive",
            },
            {
                "kind": "storage",
                "signal": "semantic date stored as character data",
                "weight": "cleanup",
            },
        ],
    }


class SemanticResolver:
    def __init__(
        self,
        *,
        store: SemanticTypeStore | None = None,
        vocabulary: SemanticVocabulary | None = None,
        config: ResolverConfig | None = None,
        evidence_widening_override: bool | None = None,
    ) -> None:
        self.store = store
        self.vocabulary = vocabulary or _get_vocabulary()
        self.config = config or ResolverConfig()
        # When set, forces the evidence-widening path on/off regardless of per-source
        # config — used by the dry-run preview endpoint to force widening on.
        self._widen_override = evidence_widening_override

    def _effective_name_tokens(self, entry: SemanticTypeEntry) -> tuple[str, ...]:
        return entry.name_tokens

    def _widen_for(self, source: str | None) -> bool:
        if self._widen_override is not None:
            return bool(self._widen_override)
        return self.config.evidence_widening_for(source)

    def resolve_table(
        self,
        *,
        source: str,
        schema: str | None,
        table: dict[str, Any],
        include_ai: bool = False,
        persist: bool = True,
        governance_context: dict[str, dict[str, Any]] | None = None,
        progress_cb: Callable[[int, int, str, ColumnProgressStatus], None] | None = None,
    ) -> dict[str, Any]:
        table_name = table.get("table_name") or table.get("name") or ""
        entity = self.resolve_entity(table)
        results = []
        findings = []
        columns = table.get("columns", []) or []
        total_columns = len(columns)
        # Batch every column's persist into a single store write — resolving a
        # whole table previously rewrote the entire YAML file once per column.
        with self.store.batch() if self.store else nullcontext():
            for index, column in enumerate(columns):
                fp: str | None = None
                existing: dict[str, Any] | None = _NOT_FETCHED
                if progress_cb is not None:
                    try:
                        col_name = str(column.get("name") or "")
                        fp = column_fingerprint(column, table)
                        # Single fetch, reused by both the progress-status read below AND
                        # resolve_column's own cache-hit check (was two separate reads of
                        # the same record -- found live 2026-08-14, see _column_progress_status).
                        existing = self.store.get(source, schema or table.get("schema_name"), table_name, col_name) if self.store else None
                        status = _column_progress_status(existing, fp)
                        progress_cb(index + 1, total_columns, col_name, status)
                    except Exception:
                        fp = None
                        existing = _NOT_FETCHED
                record = self.resolve_column(
                    source=source,
                    schema=schema or table.get("schema_name"),
                    table=table_name,
                    column=column,
                    table_facts=table,
                    entity_context=entity.get("entity"),
                    persist=persist,
                    fingerprint=fp,
                    existing=existing,
                )
                results.append(record)
                conflict_record = record.get("latest_proposal") if record.get("latest_proposal", {}).get("type_value_conflict") else record
                if conflict_record.get("type_value_conflict"):
                    findings.append(conflict_finding(conflict_record, column=column.get("name")))
        if include_ai:
            results = self._apply_ai_residuals(
                source=source,
                schema=schema,
                table=table,
                entity=entity,
                records=results,
                governance_context=governance_context,
            )
        return {"entity": entity, "columns": results, "findings": findings}

    def _apply_ai_residuals(
        self,
        *,
        source: str,
        schema: str | None,
        table: dict[str, Any],
        entity: dict[str, Any],
        records: list[dict[str, Any]],
        governance_context: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        # Attach the per-column governance context (Definition + Business Name +
        # Glossary term text, each provenance-tagged) to the residual payload so
        # the LLM sees the richest human-authored evidence — the thing only it
        # can interpret. Non-mutating: the persisted record is untouched.
        residuals: list[dict[str, Any]] = []
        for record in records:
            if not (record.get("type_id") == "unresolved"
                    or record.get("type_value_conflict")
                    or record.get("format") == "undecided"):
                continue
            col_name = str(record.get("key", "")).split("|")[-1]
            gctx = (governance_context or {}).get(col_name)
            residuals.append({**record, "governance_context": gctx} if gctx else record)
        if not residuals:
            return records
        try:
            from agents.semantic_type_agent import resolve_residual_columns
        except Exception:
            return records

        try:
            proposals = resolve_residual_columns(
                table_context={
                    "source": source,
                    "schema": schema,
                    "table": table.get("table_name") or table.get("name"),
                    "entity": entity,
                },
                residual_columns=residuals,
                vocabulary_ids=sorted(self.vocabulary.ids),
            )
        except Exception:
            return records
        if not proposals:
            return records

        by_key = {record.get("key"): record for record in records}
        for proposal in proposals:
            key = proposal.get("key")
            record = by_key.get(key)
            if not key or record is None:
                continue
            type_id = self.vocabulary.assignable_or_unresolved(proposal.get("type_id"))
            if record.get("type_id") != "unresolved" and type_id == "unresolved" and proposal.get("format"):
                updated = dict(record)
                updated["format"] = proposal.get("format")
                updated["format_source"] = "ai"
                updated["format_rationale"] = proposal.get("format_rationale") or proposal.get("rationale")
                if self.store:
                    self.store.set_record(updated, preserve_disposed=True)
                by_key[key] = updated
                continue
            updated = dict(record)
            updated["type_id"] = type_id
            updated["confidence"] = proposal.get("confidence", 0.0)
            updated["source"] = "ai"
            updated["evidence"] = list(updated.get("evidence") or []) + [{
                "kind": "ai",
                "signal": proposal.get("rationale") or "AI residual resolution",
                "weight": "proposed",
                "refs": proposal.get("evidence_refs") or [],
            }]
            if proposal.get("format"):
                updated["format"] = proposal.get("format")
                updated["format_source"] = "ai"
                updated["format_rationale"] = proposal.get("format_rationale") or proposal.get("rationale")
            if self.store:
                self.store.set_record(updated, preserve_disposed=True)
            by_key[key] = updated
        return [by_key.get(record.get("key"), record) for record in records]

    def resolve_entity(self, table: dict[str, Any]) -> dict[str, Any]:
        table_name = str(table.get("table_name") or table.get("name") or "").lower()
        table_tokens = _tokens(table_name)
        column_tokens = set()
        for column in table.get("columns", []) or []:
            column_tokens |= _tokens(str(column.get("name") or ""))

        best: tuple[str, float, list[str]] | None = None
        scored: list[tuple[str, float, list[str]]] = []
        for entity, profile in _ENTITY_PROFILES.items():
            matches: list[str] = []
            if table_tokens & profile["table_tokens"]:
                matches.append("table_name")
            matches.extend(sorted(column_tokens & profile["column_tokens"]))
            if len(matches) >= int(profile["min_matches"]):
                confidence = min(1.0, 0.45 + len(matches) * 0.12)
                scored.append((entity, confidence, matches))
                if best is None or confidence > best[1]:
                    best = (entity, confidence, matches)

        if best is None:
            return {"entity": "unresolved", "confidence": 0.0, "source": "rule", "evidence": [], "candidates": []}
        scored.sort(key=lambda item: item[1], reverse=True)
        candidates = [
            {"entity": ent, "confidence": round(conf, 4), "matched": list(mts)}
            for ent, conf, mts in scored[:2]
        ]
        return {
            "entity": best[0],
            "confidence": round(best[1], 4),
            "source": "rule",
            "evidence": [{"kind": "entity_profile", "signal": f"matched {', '.join(best[2])}", "weight": "strong"}],
            "candidates": candidates,
        }

    def resolve_column(
        self,
        *,
        source: str,
        schema: str | None,
        table: str,
        column: dict[str, Any],
        table_facts: dict[str, Any] | None = None,
        entity_context: str | None = None,
        persist: bool = True,
        fingerprint: str | None = None,
        existing: dict[str, Any] | None = _NOT_FETCHED,
    ) -> dict[str, Any]:
        column_name = column.get("name") or ""
        fingerprint = fingerprint if fingerprint is not None else column_fingerprint(column, table_facts)
        if self.store:
            # existing may already be supplied by the caller (resolve_table pre-fetches once
            # for the progress check and reuses it here, avoiding a second identical read of
            # the same record -- found live 2026-08-14). _NOT_FETCHED (not None) is the
            # "caller didn't provide one" sentinel, since a real existing value IS legitimately
            # None (no prior record).
            existing = self.store.get(source, schema, table, column_name) if existing is _NOT_FETCHED else existing
            if existing:
                fingerprint_matches = existing.get("fingerprint") == fingerprint
                version_matches = existing.get("resolver_version") == RESOLVER_VERSION
                # Accepted: always return as-is (a steward decision is sticky) -- there is no
                # more 'rejected' concept (2026-08-20, tech-debt #13/#36/#45): the only two real
                # outcomes are unresolved/pending (machine, always re-checkable) and accepted.
                if existing.get("accepted_at") and fingerprint_matches:
                    return existing
                # Machine-output records (never accepted) are deterministic scorer results that
                # differ only by confidence tier -- none are steward decisions. Serve from cache
                # when both fingerprint AND version match; re-score only when the data
                # (fingerprint) or resolver logic (version) actually changed. Omitting this
                # previously forced a full re-score + full-store YAML rewrite on every load for
                # ~36% of columns, which dominated warm element/overview latency on large sources.
                if fingerprint_matches and version_matches:
                    return existing

        date_signal = _numeric_varchar_date_signal(column)
        if date_signal:
            record = self._record_from_signal(
                source=source,
                schema=schema,
                table=table,
                column=column_name,
                signal=date_signal,
                fingerprint=fingerprint,
                entity_context=entity_context,
            )
            return self._persist(record, persist)

        # Distribution-first path: only fires when no vocabulary type at all
        # matched the column name. Columns like 'iban', 'currency', 'balance'
        # all have name tokens in the vocab and must go through the main scorer.
        # The guard uses ALL non-generic vocab types (including identifier's broad tokens)
        # to catch columns like 'counterparty_ref' which match 'identifier' token _ref.
        # NOTE: distinct from `_GENERIC_IDS` in `_score_column`. This is the smaller
        # set that decides whether the distribution-first shortcut may fire; a name
        # match against one of these generic types does NOT block the shortcut. It
        # deliberately omits `identifier` and `quantity` (which `_GENERIC_IDS`
        # includes). Different purpose, different membership — do not merge.
        _GENERIC_FALLBACK_TYPES = {"reference_code", "technical", "free_text"}
        column_name_tokens = _tokens(column.get("name") or "")
        _col_primitive = _normalise_primitive(column.get("data_type"))
        # A name match only counts as "specific" (blocking the distribution-first
        # shortcut) when the matched type can actually apply to this column's
        # primitive. Otherwise a string column named e.g. 'floating_rate_index'
        # would be vetoed by the numeric `rate` type and left unresolved.
        any_specific_name_match = any(
            _match_name(column_name_tokens, self._effective_name_tokens(entry))[0]
            for entry in self.vocabulary.entries
            if self._effective_name_tokens(entry)
            and entry.id not in _GENERIC_FALLBACK_TYPES
            and (not entry.primitive or _col_primitive in entry.primitive)
        )
        dist_signal = _distribution_first_signal(column, table_facts or {}) if not any_specific_name_match else None
        if dist_signal:
            record = self._record_from_signal(
                source=source,
                schema=schema,
                table=table,
                column=column_name,
                signal=dist_signal,
                fingerprint=fingerprint,
                entity_context=entity_context,
            )
            return self._persist(record, persist)

        # Surrogate-shape shortcut (ST-NS): a column with no specific name match
        # and no known format whose VALUES look like a system-generated id
        # (consistent mask, no whitespace, high uniqueness) → suggest surrogate.
        surrogate_signal = (
            _surrogate_shape_signal(column, table_facts or {})
            if not any_specific_name_match else None
        )
        if surrogate_signal:
            record = self._record_from_signal(
                source=source,
                schema=schema,
                table=table,
                column=column_name,
                signal=surrogate_signal,
                fingerprint=fingerprint,
                entity_context=entity_context,
            )
            return self._persist(record, persist)

        scored = self._score_column(
            column,
            table_facts or {},
            source=source,
            entity_context=entity_context,
        )
        record = self._record_from_signal(
            source=source,
            schema=schema,
            table=table,
            column=column_name,
            signal=scored,
            fingerprint=fingerprint,
            entity_context=entity_context,
        )
        return self._persist(record, persist)

    def _score_column(
        self,
        column: dict[str, Any],
        table_facts: dict[str, Any],
        *,
        source: str | None = None,
        entity_context: str | None = None,
    ) -> dict[str, Any]:
        """Tiered confidence model.

        Confidence = base (set by highest evidence tier present) + small bounded adjustments.
        Tiers: T1 Validated (0.90) · T2 Structural (0.70) · T3 Suggested (0.45) · T0 None (0.0)

        T3 base + max adjustment cap (0.08) = ~0.53 — below high_threshold by construction,
        so name-only evidence can never reach high confidence without value confirmation.
        """
        cfg = self.config
        widen = self._widen_for(source)
        # Task 6: near-miss candidates collected only under the widened path.
        near_misses: list[dict[str, Any]] = []
        name = column.get("name") or ""
        name_tokens = _tokens(name)
        primitive = _normalise_primitive(column.get("data_type"))
        samples = _samples(column)
        primary_key = set(table_facts.get("primary_key") or []) | set(table_facts.get("inferred_primary_key") or [])
        foreign_keys = {fk for rel in table_facts.get("relations") or [] for fk in rel.get("columns", [])}

        distinct = column.get("distinct_count") or 0
        row_count = column.get("row_count") or table_facts.get("row_count") or 0
        cardinality = (distinct / row_count) if row_count and distinct else 0.0

        # Generic specificity precedence (Fix 2): names that only matched a generic fallback
        # don't count as a specific name match for non-generic types.
        # NOTE: distinct from `_GENERIC_FALLBACK_TYPES` in `resolve_column`. This set
        # (which additionally includes `identifier` and `quantity`) drives the T3
        # *generic penalty* inside the scorer: a generic name match earns no promotion
        # when a more-specific type also matched. `_GENERIC_FALLBACK_TYPES` is the
        # smaller set that gates the *distribution-first shortcut*. They differ on
        # purpose and membership — do not merge.
        _GENERIC_IDS = {"natural_key", "surrogate_systemid", "reference_code", "technical", "free_text", "quantity"}

        # Check if any non-generic type has a name match — used to apply generic penalty later
        specific_name_matched_ids: set[str] = set()
        for entry in self.vocabulary.entries:
            if entry.id in _GENERIC_IDS:
                continue
            # A primitive-incompatible type can never apply to this column, so its
            # name match must not block the code/distribution path (see #4 fix).
            if entry.primitive and primitive not in entry.primitive:
                continue
            matched, _ = _match_name(name_tokens, self._effective_name_tokens(entry))
            if matched:
                specific_name_matched_ids.add(entry.id)

        candidates: list[dict[str, Any]] = []

        for entry in self.vocabulary.entries:
            evidence: list[dict[str, Any]] = []
            type_value_conflict = False

            # ── Global primitive gate ─────────────────────────────────────────
            # If the vocabulary entry restricts to specific primitives, skip any
            # column whose data-type primitive is not in that list.  This prevents
            # a BOOLEAN column from ever being scored as identifier/monetary/etc.
            if entry.primitive and primitive not in entry.primitive:
                continue

            # ── Tier 1: validator-backed (T1) ────────────────────────────────
            tier = 0
            base = 0.0
            validator_rate: float | None = None

            if entry.validator and (widen or entry.id not in _WIDEN_ONLY_VALIDATOR_TYPES):
                # Primitive gate: skip T1 validator entirely when the column's data type
                # is incompatible with this vocabulary type's allowed primitives.
                # A DOUBLE column can never be a phone number, email, or IBAN regardless
                # of what the validator returns on the numeric sample values.
                primitive_compatible = primitive in entry.primitive
                if not primitive_compatible:
                    # Skip straight to T2/T3 — no validator evaluation for this entry
                    pass
                else:
                    n_tested = len([s for s in samples if s is not None and str(s).strip()])
                    # Prefer pre-computed validator pass rate from the catalog YAML
                    precomputed = (column.get("validator_pass_rates") or {}).get(entry.validator)
                    if precomputed is not None:
                        validator_rate = precomputed
                        passing, failing = [], []
                    else:
                        validator_rate, passing, failing = run_validator_detail(entry.validator, samples)
                    if validator_rate is not None:
                        if validator_rate >= cfg.validator_decisive:
                            tier = 1
                            base = cfg.tier_validated
                            source_note = f"{_VALIDATOR_SAMPLE_LIMIT} DB values" if precomputed is not None else f"{n_tested} sample values"
                            evidence.append({
                                "kind": "validator",
                                "signal": f"{entry.validator} passed on {round(validator_rate * 100, 1)}% of {source_note}",
                                "weight": "decisive",
                                "passing": passing,
                            })
                        elif validator_rate >= cfg.validator_confirm_floor:
                            tier = 1
                            base = round(cfg.tier_validated * validator_rate, 4)
                            type_value_conflict = True
                            source_note = f"{_VALIDATOR_SAMPLE_LIMIT} DB values" if precomputed is not None else f"{n_tested} sample values"
                            detail = f" — failing: {', '.join(failing[:3])}" if failing else ""
                            evidence.append({
                                "kind": "validator",
                                "signal": (
                                    f"{entry.validator} passed on {round(validator_rate * 100, 1)}% of "
                                    f"{source_note}{detail}"
                                    + (f". Note: only {n_tested} sample values in catalog — reprofile for a larger sample." if precomputed is None and n_tested < 10 else "")
                                ),
                                "weight": "partial",
                                "passing": passing,
                                "failing": failing,
                            })
                        else:
                            # Validator refutes — only surface when name/regex had positive evidence
                            name_matched_check, matched_tok_check = _match_name(name_tokens, self._effective_name_tokens(entry))
                            regex_check = _regex_pass_rate(entry.value_regex, samples)
                            has_positive_evidence = name_matched_check or (regex_check is not None and regex_check >= 0.80)
                            if not has_positive_evidence:
                                continue
                            if name_matched_check:
                                evidence.append({"kind": "name", "signal": f"token '{matched_tok_check}' matched", "weight": "strong"})
                            if regex_check is not None and regex_check >= 0.80:
                                evidence.append({"kind": "pattern", "signal": f"regex matched {round(regex_check * 100, 1)}% of samples", "weight": "strong"})
                            inferred_pat = column.get("inferred_pattern")
                            if inferred_pat and entry.id.upper() in inferred_pat.upper():
                                evidence.append({"kind": "pattern", "signal": f"profiler detected pattern: {inferred_pat}", "weight": "strong"})
                            base = 0.30
                            type_value_conflict = True
                            source_note = f"{_VALIDATOR_SAMPLE_LIMIT} DB values" if precomputed is not None else f"{n_tested} sample values"
                            detail = f" — failing: {', '.join(failing[:3])}" if failing else ""
                            reprofile_note = (f" Note: only {n_tested} sample values tested — run Refresh Profile for a DB-level result." if precomputed is None and n_tested < 10 else "")
                            evidence.append({
                                "kind": "validator",
                                "signal": (f"{entry.validator} passed on only {round(validator_rate * 100, 1)}% of {source_note}{detail}. Values refute this type.{reprofile_note}"),
                                "weight": "refutes",
                                "failing": failing,
                                "passing": passing,
                            })
                            candidates.append({
                                "type_id": entry.id,
                                "score": round(base, 4),
                                "base": round(base, 4),
                                "adjustments": [],
                                "tier": 1,
                                "had_name_match": name_matched_check,
                                "domain_role": _CATEGORY_TO_DOMAIN_ROLE.get(entry.category, "unresolved"),
                                "evidence": evidence,
                                "type_value_conflict": True,
                            })
                            continue

            # ── Tier 2: strong structural (T2) ───────────────────────────────
            if tier < 1:
                regex_rate = _regex_pass_rate(entry.value_regex, samples)
                if regex_rate is not None and regex_rate >= 0.80:
                    tier = 2
                    base = cfg.tier_structural
                    evidence.append({
                        "kind": "pattern",
                        "signal": f"regex matched {round(regex_rate * 100, 1)}% of samples",
                        "weight": "strong",
                    })
                elif regex_rate is not None and regex_rate < 0.80:
                    name_matched_here, _ = _match_name(name_tokens, self._effective_name_tokens(entry))
                    if name_matched_here:
                        type_value_conflict = True
                        evidence.append({
                            "kind": "pattern",
                            "signal": f"regex matched only {round(regex_rate * 100, 1)}% of samples",
                            "weight": "refutes",
                        })

                # Distribution-confirmed T2 (for types whose confirmation_kind is distribution)
                if tier < 1 and tier != 2 and entry.confirmation_kind == "distribution" and not specific_name_matched_ids:
                    if entry.category in {"code", "classification"} and 0 < distinct <= 50 and cardinality <= 0.15:
                        tier = 2
                        base = cfg.tier_structural
                        evidence.append({
                            "kind": "distribution",
                            "signal": f"{distinct} distinct values — low cardinality confirms code/enumeration",
                            "weight": "strong",
                        })
                    elif entry.category == "surrogate_id" and cardinality >= 0.9 and name in primary_key:
                        tier = 2
                        base = cfg.tier_structural
                        evidence.append({
                            "kind": "distribution",
                            "signal": f"high uniqueness ({round(cardinality * 100, 1)}%) + PK membership confirms identifier",
                            "weight": "strong",
                        })
            else:
                # T1 already set — still check regex for corroborating evidence (don't change tier)
                regex_rate = _regex_pass_rate(entry.value_regex, samples)
                if regex_rate is not None and regex_rate >= 0.80:
                    evidence.append({
                        "kind": "pattern",
                        "signal": f"regex matched {round(regex_rate * 100, 1)}% of samples (corroborating)",
                        "weight": "strong",
                    })

            # ── Tier 2 supplement: numeric dtype + name match → T2 for monetary/rate ──
            # monetary_amount and rate have confirmation_kind=none but a numeric column
            # with a name match is structurally confirmed (values ARE the right primitive).
            if tier == 0 and entry.category in {"monetary", "rate"} and primitive in {"integer", "decimal"}:
                name_matched_check, token_check = _match_name(name_tokens, self._effective_name_tokens(entry))
                if name_matched_check:
                    tier = 2
                    base = cfg.tier_structural
                    evidence.append({
                        "kind": "schema",
                        "signal": f"numeric column '{name}' with monetary/rate name token '{token_check}'",
                        "weight": "strong",
                    })

            # ── Tier 2 (shape): flag-gated shape initiation (U1a) ─────────────
            # Only under evidence widening. For confirmation_kind: shape types still
            # at tier 0, evaluate the vocab's any_of/none_of detectors. A none_of gate
            # suppresses initiation; ≥2 any_of signals (or 1 + a conjunct) → strong T2;
            # exactly 1 signal → weak sub-band (0.55). Name token becomes a corroborator,
            # not a gate. The 'quantity' generic type only lands when no specific
            # monetary/rate candidate already initiated.
            if widen and tier == 0 and entry.confirmation_kind == "shape":
                shape_spec = entry.detectors.get("shape") or {}
                shape_meta = dict(column)
                shape_meta.setdefault("row_count", table_facts.get("row_count") or row_count)
                none_fired = _eval_shape_list(
                    shape_spec.get("none_of"), values=samples, meta=shape_meta, table_dict=table_facts
                )
                any_fired = _eval_shape_list(
                    shape_spec.get("any_of"), values=samples, meta=shape_meta, table_dict=table_facts
                )
                name_matched_shape, tok_shape = _match_name(name_tokens, self._effective_name_tokens(entry))
                if none_fired:
                    near_misses.append({
                        "type_id": entry.id,
                        "blocked_by": "; ".join(f"{n}: {r['detail']}" for n, r in none_fired),
                        "evidence": [
                            {"kind": "shape", "signal": r["detail"], "weight": "refutes"}
                            for _, r in none_fired
                        ],
                    })
                elif entry.id == "quantity":
                    # Generic numeric landing zone — only when no specific measure/rate
                    # candidate already reached tier ≥ 2, and a generic signal fired.
                    specific_measure = any(
                        c.get("tier", 0) >= 2 and c.get("type_id") in {"monetary_amount", "rate"}
                        for c in candidates
                    )
                    if any_fired and not specific_measure:
                        tier = 2
                        base = 0.55  # weak sub-band → suggested routing band by construction
                        for _, r in any_fired:
                            evidence.append({"kind": "shape", "signal": r["detail"], "weight": "moderate"})
                        evidence.append({
                            "kind": "shape",
                            "signal": "numeric measure with no specific monetary/rate signal",
                            "weight": "moderate",
                        })
                    elif any_fired:
                        near_misses.append({
                            "type_id": entry.id,
                            "blocked_by": "a specific measure/rate type initiated instead",
                            "evidence": [
                                {"kind": "shape", "signal": r["detail"], "weight": "weak"}
                                for _, r in any_fired
                            ],
                        })
                else:
                    n = len(any_fired)
                    conjunct = shape_detectors.currency_sibling(table_facts) or bool(
                        entity_context and entity_context != "unresolved"
                    )
                    if n >= 2 or (n == 1 and conjunct):
                        tier = 2
                        base = cfg.tier_structural  # 0.70
                        for _, r in any_fired:
                            evidence.append({"kind": "shape", "signal": r["detail"], "weight": "strong"})
                        if n == 1 and conjunct:
                            evidence.append({
                                "kind": "context",
                                "signal": "corroborated by currency sibling / entity context",
                                "weight": "moderate",
                            })
                        if name_matched_shape:
                            evidence.append({
                                "kind": "name",
                                "signal": f"name token '{tok_shape}' corroborates",
                                "weight": "moderate",
                            })
                    elif n == 1:
                        tier = 2
                        base = 0.55  # weak sub-band → suggested routing band by construction
                        for _, r in any_fired:
                            evidence.append({"kind": "shape", "signal": r["detail"], "weight": "moderate"})
                        if name_matched_shape:
                            evidence.append({
                                "kind": "name",
                                "signal": f"name token '{tok_shape}' corroborates",
                                "weight": "weak",
                            })
                    elif name_matched_shape or (entity_context and entity_context != "unresolved"):
                        near_misses.append({
                            "type_id": entry.id,
                            "blocked_by": "no initiating shape signal fired; corroborators only",
                            "evidence": [
                                {"kind": "schema", "signal": f"data type {primitive} fits", "weight": "weak"}
                            ],
                        })

            # ── Tier 3: name/structural suggestion (T3) ──────────────────────
            if tier == 0:
                name_matched, matched_token = _match_name(name_tokens, self._effective_name_tokens(entry))
                if name_matched:
                    # name-vs-free_text char-type guard (ST-NS): a person/entity
                    # NAME cannot be numeric/alphanumeric. If the column's values
                    # carry digits, this is not a name — drop the candidate so it
                    # falls to free_text/unresolved instead of a wrong "Name".
                    if entry.category == "name":
                        _nm = _value_shape_metrics(column)
                        # Only reject when the values look like uniform CODES
                        # (consistent mask, no spaces, mostly digits, near-constant
                        # length) — NOT names with incidental digits like "3M" or
                        # "A1 Trading", which are legitimate organisation names.
                        if (_nm and _nm["mask_coverage"] >= 0.8
                                and not _nm["has_whitespace"]
                                and _nm["digit_ratio"] >= 0.5
                                and _nm["length_cv"] <= 0.2):
                            continue
                    # Fix 2: generic penalty — generic beats nothing, not a specific match
                    if entry.id in _GENERIC_IDS and specific_name_matched_ids - {entry.id}:
                        # A more-specific type matched; generic gets no promotion
                        pass
                    else:
                        tier = 3
                        base = cfg.tier_suggested
                        evidence.append({
                            "kind": "name",
                            "signal": f"token '{matched_token}' matched",
                            "weight": "moderate",
                        })
                elif name in primary_key and entry.category == "surrogate_id":
                    tier = 3
                    base = cfg.tier_suggested
                    evidence.append({
                        "kind": "structural",
                        "signal": "column participates in the primary key",
                        "weight": "moderate",
                    })
                elif name in foreign_keys and entry.category == "surrogate_id":
                    tier = 3
                    base = cfg.tier_suggested
                    evidence.append({
                        "kind": "structural",
                        "signal": "column participates in a relation",
                        "weight": "moderate",
                    })

            if tier == 0:
                continue  # no evidence at all — skip this candidate

            # Value-shape corroboration (display-only — never adjusts the score).
            # For identifier-category types, a highly consistent value LENGTH is a
            # human-meaningful signal (the heuristic "fixed-width alphanumeric =
            # identifier"). It matters MORE when uniqueness / PK signals are weak
            # (e.g. a foreign key that isn't unique or is sparsely populated), so it
            # is attached regardless of uniqueness. A consistent character *pattern*
            # (mask) is a bonus on top of consistent length, not a requirement — a
            # hex hash id has fixed length but a random letter/digit mask.
            if entry.category in {"natural_id", "surrogate_id"}:
                _shape_metrics = _value_shape_metrics(column)
                if _shape_metrics and _shape_metrics["length_cv"] <= 0.10:
                    if _shape_metrics["mask_coverage"] >= 0.90:
                        _shape_share = int(round(_shape_metrics["mask_coverage"] * 100))
                        _shape_signal = (
                            f"consistent length and character pattern ({_shape_share}% share one shape)"
                        )
                    else:
                        _shape_len = int(round(_shape_metrics["mean_len"]))
                        _shape_signal = f"fixed value length (~{_shape_len} characters across all values)"
                    evidence.append({
                        "kind": "shape",
                        "signal": _shape_signal,
                        "weight": "weak",
                    })

            # ── Adjustments (capped, confirmed sources only) ─────────────────
            adjustment = 0.0
            adj_items: list[dict[str, Any]] = []

            if primitive in entry.primitive:
                evidence.append({
                    "kind": "schema",
                    "signal": f"data type {primitive} is allowed for this type",
                    "weight": "weak",
                })
                adjustment += 0.02
                adj_items.append({"label": f"Data type ({primitive}) fits", "points": 0.02})

            if entity_context == "Account" and entry.id in {"natural_key", "surrogate_systemid", "monetary_amount", "currency_code", "reference_code"}:
                evidence.append({"kind": "entity", "signal": "Account entity context supports this type", "weight": "weak"})
                adjustment += 0.03
                adj_items.append({"label": "Account entity context", "points": 0.03})
            elif entity_context == "Counterparty" and entry.id in {"natural_key", "surrogate_systemid", "natural_lei", "country_code", "name", "reference_code"}:
                evidence.append({"kind": "entity", "signal": "Counterparty entity context supports this type", "weight": "weak"})
                adjustment += 0.03
                adj_items.append({"label": "Counterparty entity context", "points": 0.03})

            # SD-R4: the confirmed-glossary-link / approved-definition confidence nudges
            # were removed here (2026-08-12) — the interpretation-set submit gate already
            # requires the semantic type to be Accepted BEFORE a definition/glossary link
            # can reach approved/confirmed, so neither signal could ever be a genuine input
            # to the type decision it fired after. Measured: removing them changed 0 of 54
            # governance-carrying columns' outcome. Removing them from scoring (not just the
            # fingerprint) keeps the resolver fully deterministic on data + naming.

            adjustment = min(adjustment, cfg.adjustment_cap)
            final_score = round(min(1.0, base + adjustment), 4)

            candidates.append({
                "type_id": entry.id,
                "score": final_score,
                "base": round(base, 4),
                "adjustments": adj_items,
                "tier": tier,
                "domain_role": "key" if name in primary_key and entry.category in {"natural_id", "surrogate_id"} else _CATEGORY_TO_DOMAIN_ROLE.get(entry.category, "unresolved"),
                "evidence": evidence,
                "type_value_conflict": type_value_conflict,
            })

        candidates.sort(key=lambda item: item["score"], reverse=True)
        top = candidates[0] if candidates else None

        if not top or top["score"] < cfg.suggested_threshold:
            # Special case: top candidate is a refuted type that had a name match
            # (e.g. IBAN column where values have bad checksums).
            # In this case the steward needs to see the conflict clearly, not just
            # "Unresolved" — route to 'suggested' with the conflicted type_id.
            if top and top.get("type_value_conflict") and top.get("had_name_match"):
                return {
                    "type_id": top["type_id"],
                    "domain_role": top["domain_role"],
                    "confidence": top["score"],
                    "tier": top.get("tier", 0),
                    "candidates": [{"type_id": c["type_id"], "score": c["score"]} for c in candidates[:5]],
                    "evidence": top["evidence"],
                    "type_value_conflict": True,
                    "score_breakdown": _build_breakdown(top, cfg.adjustment_cap),
                }
            unresolved_result = {
                "type_id": "unresolved",
                "domain_role": "unresolved",
                "confidence": 0.0 if not top else top["score"],
                "tier": 0,
                # Always surface top candidates so the steward sees what came closest,
                # even if every score was 0 (no evidence at all).
                "candidates": [{"type_id": c["type_id"], "score": c["score"]} for c in candidates[:5]] if candidates else [],
                "evidence": [] if not top else top["evidence"],
                "type_value_conflict": bool(top and top.get("type_value_conflict")),
                "score_breakdown": _build_breakdown(top, cfg.adjustment_cap) if top and top.get("score") else None,
                "ai_available": True,  # hint to UI that include_ai=true would help
            }
            # Task 6: additive structured-unresolved fields — only under the widened
            # path, so flag-off output stays byte-identical. Frontend ignores unknown keys.
            if widen:
                if not top:
                    reason = "corroboration_without_initiation" if near_misses else "no_signal"
                elif top.get("type_value_conflict"):
                    reason = "conflict"
                elif top.get("score", 0.0) > 0:
                    reason = "below_floor"
                elif near_misses:
                    reason = "corroboration_without_initiation"
                else:
                    reason = "no_signal"
                unresolved_result["resolution_reason"] = reason
                if near_misses:
                    unresolved_result["nearest_candidates"] = near_misses[:3]
            return unresolved_result

        # Above suggested_threshold: the persisted disposition no longer distinguishes a
        # high-confidence guess from a low-confidence one (2026-08-20, tech-debt #36) --
        # `confidence` alone carries that, read directly by the UI's High/Medium/Low grade
        # and by DQ scoring's own floor_threshold comparison.
        return {
            "type_id": top["type_id"],
            "domain_role": top["domain_role"],
            "confidence": top["score"],
            "tier": top.get("tier", 0),
            "candidates": [{"type_id": c["type_id"], "score": c["score"]} for c in candidates[:5]],
            "evidence": top["evidence"],
            "type_value_conflict": bool(top.get("type_value_conflict")),
            "score_breakdown": _build_breakdown(top, cfg.adjustment_cap),
        }

    def _record_from_signal(
        self,
        *,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        signal: dict[str, Any],
        fingerprint: str,
        entity_context: str | None = None,
    ) -> dict[str, Any]:
        type_id = signal.get("type_id", "unresolved")
        # Derive scope, pii, entity from vocabulary entry. Resolve legacy aliases
        # (pre-split 'identifier') so persisted/aliased ids still find an entry.
        entry = self.vocabulary.get(_LEGACY_TYPE_ALIASES.get(type_id, type_id))
        scope = _SCOPE_SOURCE_TO_SCOPE.get(entry.scope_source, "internal") if entry else None
        pii = entry.pii.get("is_pii", False) if entry else False
        pii_category = entry.pii.get("category") if entry and pii else None
        entity = signal.get("entity") or entity_context
        record = {
            "key": SemanticTypeStore.key(source, schema, table, column),
            "type_id": type_id,
            "domain_role": signal.get("domain_role", "unresolved"),
            "confidence": max(0.0, min(1.0, float(signal.get("confidence") or 0.0))),
            "source": "rule",
            "candidates": signal.get("candidates") or [{"type_id": type_id, "score": signal.get("confidence", 0.0)}],
            "evidence": signal.get("evidence") or [],
            # SD-R1 one field of truth (B1): `_record_from_signal` is the single builder
            # every path funnels through. Shortcut signals (distribution-first, varchar-
            # date) carry `tier` only inside `score_breakdown`; fall back to it here so the
            # persisted top-level `tier` always equals `score_breakdown.tier`. Invariant
            # enforced by tests. No confidence changes — only `tier` becomes consistent.
            "tier": signal.get("tier", (signal.get("score_breakdown") or {}).get("tier", 0)),
            "score_breakdown": signal.get("score_breakdown"),
            "type_value_conflict": bool(signal.get("type_value_conflict") or signal.get("conflict")),
            "type_datatype_difference": bool(signal.get("type_datatype_difference") or signal.get("storage_mismatch")),
            "format": signal.get("format"),
            "format_source": signal.get("format_source"),
            "format_rationale": signal.get("format_rationale"),
            "scope": scope,
            "entity": entity,
            "pii": pii,
            "pii_category": pii_category,
            "resolver_version": RESOLVER_VERSION,
            "resolved_at": datetime.now().isoformat(),
            "accepted_by": None,
            "accepted_by_role": None,
            "accepted_at": None,
            "fingerprint": fingerprint,
        }
        # Task 6: additive structured-unresolved fields — only present when the widened
        # path populated them, so flag-off records are byte-identical to pre-U1a.
        if signal.get("resolution_reason") is not None:
            record["resolution_reason"] = signal["resolution_reason"]
        if signal.get("nearest_candidates") is not None:
            record["nearest_candidates"] = signal["nearest_candidates"]
        return record

    def _persist(self, record: dict[str, Any], persist: bool) -> dict[str, Any]:
        if persist and self.store:
            return self.store.set_record(record, preserve_disposed=True)
        return record
