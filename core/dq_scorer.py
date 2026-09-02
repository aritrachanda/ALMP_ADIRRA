"""DQ scoring engine — pure, deterministic, hand-recalculable.

Implements the column scoring pipeline of DQ-Scoring-Model-Design-v1.md
(§1 pipeline, §4 component models, §5 formula families, §6 reallocation,
§7 grade bands). Headless in U2a: this module computes and returns a
breakdown record; nothing here renders it and ``_quality_grade()`` is
untouched.

The scorer is pure — every input is passed in (profiler facts + governance
signals + intent + the confirmed semantic record). Persistence, fingerprints
and event wiring live in ``core.dq_score_store`` / ``core.dq_service``.

Rounding law (§5): line-items to 1 decimal; scaled components to 2 decimals;
the overall score is the only integer rounding, applied once at the end.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from core.dq_archetype import accepted_semantic_type, detect_archetype
from core.dq_config import DQScoringConfig
from core.semantic_resolver import DEFAULT_FLOOR_THRESHOLD
from core.dq_remediation import (
    derive_actions,
    inapplicable_components,
    path_to_next_grade,
)

ColumnDict = dict[str, Any]

# Shape version of the emitted breakdown — bumped whenever the scorer adds or
# changes *display* fields that the input-signal fingerprint cannot see (e.g.
# U2d's per-line-item ``evidence_note``). The store/service use it as an extra
# cache-invalidation key so records written by an older scorer shape are healed
# on next view, without churning score history (DQ §16.3–16.4).
#   1 = pre-U2d (no evidence_note)   ·   2 = U2d evidence_note per line-item
#   3 = U4b remediation actions + path-to-next-grade + inapplicable_components
#   4 = U4b-fix gap-aware plain-language actions + per-action destination
#       (resulting_score/grade) + path landing_score/grade
#   5 = Polish Batch: Findings-overlay checks hint, specific outlier wording,
#       path `any_one_suffices` tie flag
#   6 = U6b: Semantic (4th) component flipped live — records heal to the
#       4-component breakdown (Semantic block, "confirm the semantic type"
#       action, governance re-weight visible)
#   7 = SD-R3c: Definition renamed Interpretation and the Semantic Type folded
#       in as an Interpretation line-item (4th component retired); components
#       re-weighted Profile 50 / Interpretation 30 / Reference Data 20 with
#       line-items summing natively to their block (no reweight factor) — every
#       stored record heals to the 3-component Interpretation breakdown
BREAKDOWN_VERSION = 7


# ── rounding helpers ─────────────────────────────────────────────────────────

def _q(value: Any, places: int) -> Decimal:
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _round(value: Any, places: int = 1) -> float:
    return float(_q(value, places))


def _round_int(value: Any) -> int:
    return int(_q(value, 0))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _note_tail(earned: float, max_d: float) -> str:
    """Trailing '→ full X/Y' (or '→ X/Y') fragment shared by evidence notes."""
    return f"full {earned}/{max_d}" if earned >= max_d else f"{earned}/{max_d}"


def grade_for(score: float, config: DQScoringConfig) -> dict[str, Any]:
    """Band lookup (§7): first descending band whose ``min`` the score meets."""
    for band in config.grade_bands:
        if score >= band["min"]:
            return {"label": band.get("label"), "color_intent": band.get("color_intent")}
    last = config.grade_bands[-1]
    return {"label": last.get("label"), "color_intent": last.get("color_intent")}


def _tab_grade(earned: float, max_d: float, config: DQScoringConfig) -> dict[str, Any]:
    if not max_d:
        return {"label": None, "color_intent": None}
    return grade_for(_round_int(100 * earned / max_d), config)


# ── intent resolution ────────────────────────────────────────────────────────

def _resolve_intent(intent: dict[str, Any] | None, config: DQScoringConfig) -> dict[str, Any]:
    defaults = config.column_intent_defaults or {}
    intent = intent or {}
    return {
        "nullability": intent.get("nullability") or defaults.get("nullability", "unspecified"),
        "date_role": intent.get("date_role") or defaults.get("date_role", "unspecified"),
        "criticality": intent.get("criticality") or defaults.get("criticality", "standard"),
        "placeholder_exceptions": intent.get("placeholder_exceptions")
        or defaults.get("placeholder_exceptions", []),
    }


# ── finding routing (§4.1, F4) ───────────────────────────────────────────────

def _route_finding(
    finding: dict[str, Any], archetype_dims: set[str], dimension_category_map: dict[str, str]
) -> str:
    """Return the dimension a finding lands in, or ``'findings'`` (overlay).

    AI-provenance findings always land in the overlay (advisory). A rule
    finding routes to its mapped dimension when that dimension exists for the
    archetype; otherwise (dimension absent, or category unmapped) it falls to
    the overlay. Nothing is silently dropped.
    """
    if str(finding.get("provenance", "rule")) == "ai":
        return "findings"
    mapped = dimension_category_map.get(str(finding.get("category")))
    if mapped and mapped in archetype_dims:
        return mapped
    return "findings"


# ── Profile component (§4.1) ─────────────────────────────────────────────────

def _score_completeness(col_dict: ColumnDict, max_d: float, intent: dict, config: DQScoringConfig,
                        attached: list) -> dict:
    tol = config.tolerances or {}
    row_count = col_dict.get("row_count") or 0
    nullability = intent["nullability"]
    null_count = col_dict.get("null_count") or 0
    counted_nulls = null_count if nullability in {"mandatory", "unspecified"} else 0
    empty = col_dict.get("empty_string_count") or 0
    placeholder_count = col_dict.get("placeholder_count") or 0
    placeholder_weight = float(tol.get("placeholder_weight", 0.5))
    zero_at_map = tol.get("completeness_zero_at", {}) or {}
    zero_at = float(zero_at_map.get(nullability, 0.25))

    if row_count:
        effective_missing = (counted_nulls + empty + placeholder_weight * placeholder_count) / row_count
    else:
        effective_missing = 0.0
    earned = _round(max_d * _clamp01(1 - effective_missing / zero_at) if zero_at else max_d, 1)
    missing_pct = round(effective_missing * 100, 1)
    tol_pct = round(zero_at * 100, 1)
    within = "within" if effective_missing <= zero_at else "beyond"
    note = (
        f"{missing_pct}% of values are missing (nulls, empties, placeholders), "
        f"{within} the {tol_pct}% tolerance → {_note_tail(earned, max_d)}."
    )
    return {
        "label": "Completeness",
        "validation": f"effective missing rate vs completeness_zero_at[{nullability}]={zero_at}",
        "formula": f"{max_d} × (1 − {round(effective_missing, 4)}/{zero_at})",
        "evidence_note": note,
        "earned": earned,
        "max": max_d,
        "evidence": {
            "row_count": row_count, "null_count": null_count,
            "empty_string_count": empty, "placeholder_count": placeholder_count,
            "placeholder_weight": placeholder_weight, "nullability": nullability,
        },
        "findings": [f for f in attached],
    }


def _score_validity(col_dict: ColumnDict, max_d: float, intent: dict, config: DQScoringConfig,
                    validator_yardstick: float | None, attached: list) -> dict:
    tol = config.tolerances or {}
    row_count = col_dict.get("row_count") or 0
    zero_at = float(tol.get("validity_zero_at", 0.10))

    if validator_yardstick is not None:
        invalid_rate = _clamp01(1 - validator_yardstick)
        formula = f"{max_d} × (1 − validator_invalid {round(invalid_rate, 4)}/{zero_at})"
        evidence = {"validator_pass_rate": round(validator_yardstick, 4), "yardstick": "validator"}
    else:
        invalid_format = col_dict.get("invalid_format_count") or 0
        type_mismatch = col_dict.get("type_mismatch_count") or 0
        suspicious = col_dict.get("suspicious_date_count") or 0
        counted_future = (col_dict.get("future_date_count") or 0) if intent["date_role"] == "past_only" else 0
        invalid_rate = (invalid_format + type_mismatch + counted_future + suspicious) / row_count if row_count else 0.0
        formula = f"{max_d} × (1 − {round(invalid_rate, 4)}/{zero_at})"
        evidence = {
            "invalid_format_count": invalid_format, "type_mismatch_count": type_mismatch,
            "suspicious_date_count": suspicious, "future_date_count": col_dict.get("future_date_count"),
            "date_role": intent["date_role"], "inferred_pattern": col_dict.get("inferred_pattern"),
            "pattern_confidence": col_dict.get("pattern_confidence"),
        }
    earned = _round(max_d * _clamp01(1 - invalid_rate / zero_at) if zero_at else max_d, 1)
    invalid_pct = round(invalid_rate * 100, 1)
    tol_pct = round(zero_at * 100, 1)
    within = "within" if invalid_rate <= zero_at else "beyond"
    yard = "the confirmed validator" if validator_yardstick is not None else "format/type validation"
    note = (
        f"{invalid_pct}% of values fail {yard}, {within} the {tol_pct}% tolerance "
        f"→ {_note_tail(earned, max_d)}."
    )
    return {
        "label": "Validity", "validation": "conformance to detected format/type or validator",
        "formula": formula, "evidence_note": note, "earned": earned, "max": max_d,
        "evidence": evidence, "findings": [f for f in attached],
    }


def _score_uniqueness(col_dict: ColumnDict, max_d: float, attached: list) -> dict:
    uniqueness_pct = col_dict.get("uniqueness_pct")
    earned = _round(max_d * float(uniqueness_pct), 1) if uniqueness_pct is not None else _round(max_d, 1)
    distinct_pct = round((float(uniqueness_pct) if uniqueness_pct is not None else 1.0) * 100, 1)
    note = f"{distinct_pct}% distinct values → {_note_tail(earned, max_d)}."
    return {
        "label": "Uniqueness", "validation": "is a key actually a key",
        "formula": f"{max_d} × {uniqueness_pct}", "evidence_note": note, "earned": earned, "max": max_d,
        "evidence": {
            "uniqueness_pct": uniqueness_pct, "duplicate_count": col_dict.get("duplicate_count"),
            "distinct_count": col_dict.get("distinct_count"),
        },
        "findings": [f for f in attached],
    }


def _score_consistency(archetype: str, col_dict: ColumnDict, max_d: float, config: DQScoringConfig,
                       attached: list) -> dict:
    ded_cfg = config.consistency_deductions or {}
    tol = config.tolerances or {}
    row_count = col_dict.get("row_count") or 0
    is_numeric = archetype == "numeric"
    is_key = archetype == "key_like"
    is_coded = archetype == "coded"

    deductions: list[dict[str, Any]] = []
    stddev = col_dict.get("numeric_stddev")
    distinct = col_dict.get("distinct_count")
    if not is_key and ((stddev is not None and stddev == 0) or (distinct == 1 and row_count > 1)):
        deductions.append({"name": "single_constant", "points": float(ded_cfg.get("single_constant", 8))})
    if col_dict.get("constant_run_warning"):
        deductions.append({"name": "constant_run", "points": float(ded_cfg.get("constant_run", 6))})
    if is_numeric:
        outlier_count = col_dict.get("numeric_outlier_count")
        if outlier_count and row_count:
            outlier_rate = outlier_count / row_count
            outlier_zero_at = float(tol.get("outlier_zero_at", 0.05))
            penalty = max_d * min(1.0, outlier_rate / outlier_zero_at) if outlier_zero_at else 0.0
            deductions.append({"name": "outlier_penalty", "points": round(penalty, 4),
                               "outlier_rate": round(outlier_rate, 4)})
    if not is_coded and not is_key:
        top = col_dict.get("top_values") or []
        if top and row_count:
            top_share = (top[0].get("count", 0) or 0) / row_count
            if top_share >= float(tol.get("dominance_threshold", 0.98)):
                deductions.append({"name": "dominance", "points": float(ded_cfg.get("dominance", 4))})

    total_ded = sum(d["points"] for d in deductions)
    earned = _round(max(0.0, max_d - total_ded), 1)
    if deductions:
        names = ", ".join(str(d["name"]).replace("_", " ") for d in deductions)
        note = f"{round(total_ded, 1)} point(s) deducted for {names} → {earned}/{max_d}."
    else:
        note = f"no consistency deductions → {_note_tail(earned, max_d)}."
    return {
        "label": "Consistency", "validation": "plausibility / single-column consistency",
        "formula": f"{max_d} − {round(total_ded, 4)}", "evidence_note": note, "earned": earned, "max": max_d,
        "evidence": {
            "deductions": deductions, "numeric_stddev": stddev, "numeric_avg": col_dict.get("numeric_avg"),
            "numeric_median": col_dict.get("numeric_median"),
            "numeric_outlier_count": col_dict.get("numeric_outlier_count"),
            "outlier_detection": col_dict.get("outlier_detection"),
            "distinct_count": distinct, "uniqueness_pct": col_dict.get("uniqueness_pct"),
        },
        "findings": [f for f in attached],
    }


# Plain-language reminder of what this catch-all line-item actually considers
# (Polish Batch Task 1): regulatory-pattern / metadata findings that have no
# scored dimension on this archetype, plus every AI-detected finding (any
# category), which always lands here as advisory evidence rather than a
# rule-grade deduction. Purely descriptive — appended to the note, never scored.
_OVERLAY_CHECKS_HINT = (
    "checks: regulatory-pattern and metadata findings (e.g. undeclared keys, "
    "missing descriptions) plus any AI-detected observation"
)


def _score_findings_overlay(max_d: float, overlay_findings: list) -> dict:
    sev_points = {"high": 4, "attention": 2, "info": 0.5}
    prov_mult = {"rule": 1.0, "ai": 0.5}
    total = 0.0
    for f in overlay_findings:
        total += sev_points.get(str(f.get("severity")), 0.0) * prov_mult.get(str(f.get("provenance", "rule")), 1.0)
    earned = _round(max(0.0, max_d - total), 1)
    if overlay_findings:
        note = f"{len(overlay_findings)} finding(s) deducted {round(total, 1)} point(s) → {earned}/{max_d}."
    else:
        note = f"no open findings → {_note_tail(earned, max_d)}."
    note = f"{note} ({_OVERLAY_CHECKS_HINT})."
    return {
        "label": "Findings overlay", "validation": "findings with no home dimension + AI-advisory",
        "formula": f"{max_d} − {round(total, 4)}", "evidence_note": note, "earned": earned, "max": max_d,
        "evidence": {}, "findings": [f for f in overlay_findings],
    }


def _score_profile(archetype: str, col_dict: ColumnDict, intent: dict, findings: list,
                   validator_yardstick: float | None, config: DQScoringConfig) -> dict:
    dims = config.profile_dimensions.get(archetype, {})
    routing = config.finding_routing or {}
    dim_cat_map = routing.get("dimension_category_map", {}) or {}
    scored_dims = {k for k in dims if k != "findings"}

    # Route findings: attach to a present dimension (evidence only) or overlay.
    by_dim: dict[str, list] = {}
    overlay: list = []
    for f in findings or []:
        dest = _route_finding(f, scored_dims, dim_cat_map)
        if dest == "findings":
            overlay.append(f)
        else:
            by_dim.setdefault(dest, []).append(f)

    line_items: list[dict] = []
    if "completeness" in dims:
        line_items.append(_score_completeness(col_dict, dims["completeness"], intent, config,
                                              by_dim.get("completeness", [])))
    if "validity" in dims:
        line_items.append(_score_validity(col_dict, dims["validity"], intent, config,
                                          validator_yardstick, by_dim.get("validity", [])))
    if "uniqueness" in dims:
        line_items.append(_score_uniqueness(col_dict, dims["uniqueness"], by_dim.get("uniqueness", [])))
    if "consistency" in dims:
        line_items.append(_score_consistency(archetype, col_dict, dims["consistency"], config,
                                             by_dim.get("consistency", [])))
    if "findings" in dims:
        line_items.append(_score_findings_overlay(dims["findings"], overlay))

    earned = _round(sum(li["earned"] for li in line_items), 1)
    base_max = float(sum(dims.values()))
    return {"name": "profile", "earned": earned, "base_max": base_max, "line_items": line_items}


# ── Definition component (§4.2) ──────────────────────────────────────────────

def _score_interpretation(definition: dict | None, business_name: dict | None,
                         glossary: dict | None, semantic_record: dict | None,
                         config: DQScoringConfig) -> dict:
    """Score the Interpretation component (SD-R3c — renamed from Definition).

    Four line-items — Definition, Business Name, Glossary Linkage, Semantic Type
    — whose maxima sum natively to the Interpretation weight (30). Semantic Type
    was the retired 4th 'semantic' component, folded in here as a line-item; its
    scoring logic is unchanged (``_semantic_line_item``). No scale factor is
    applied anywhere: the literals below are already on the composite scale.
    """
    scales = config.definition_scales or {}
    definition = definition or {}
    business_name = business_name or {}
    glossary = glossary or {}

    maxes = config._interpretation_line_item_maxes()
    def_max = int(maxes["Definition"])
    bn_max = int(maxes["Business Name"])
    gl_max = int(maxes["Glossary Linkage"])

    desc_scale = scales.get("description", {}) or {}
    lifecycle_scale = desc_scale.get("lifecycle", {}) or {}
    present = bool(definition.get("present"))
    if present:
        d_present = desc_scale.get("present", 3)
        d_author = desc_scale.get("authorship_ai", 1) if definition.get("is_ai") else desc_scale.get("authorship_human", 3)
        lifecycle = definition.get("lifecycle", "draft")
        d_life = lifecycle_scale.get(lifecycle, 0)
        def_earned = float(d_present + d_author + d_life)
        def_formula = f"{d_present} + {d_author} + {d_life}"
    else:
        def_earned = 0.0
        def_formula = "absent → 0"
    def_earned_r = _round(def_earned, 1)
    if present:
        author = "AI-drafted but not steward-reviewed" if definition.get("is_ai") else "human-authored"
        def_note = (
            f"description present, {author}, lifecycle '{definition.get('lifecycle', 'draft')}' "
            f"→ {_note_tail(def_earned_r, def_max)}."
        )
    else:
        def_note = f"no description recorded → 0/{def_max}; adding one starts earning definition points."
    definition_item = {
        "label": "Definition", "formula": def_formula, "evidence_note": def_note,
        "earned": def_earned_r, "max": def_max,
        "evidence": {"present": present, "is_ai": bool(definition.get("is_ai")),
                     "lifecycle": definition.get("lifecycle")},
    }

    bn_scale = scales.get("business_name", {}) or {}
    bn_source = business_name.get("source", "none")
    bn_earned = float(bn_scale.get(bn_source, 0))
    bn_earned_r = _round(bn_earned, 1)
    if bn_source == "human":
        bn_note = f"business name is steward-assigned → {_note_tail(bn_earned_r, bn_max)}."
    elif bn_earned_r == 0:
        bn_note = f"no business name yet → 0/{bn_max}; assigning one earns up to {bn_max} points."
    else:
        bn_note = (
            f"business name is AI/auto-derived, not steward-assigned → {bn_earned_r}/{bn_max}; "
            f"assigning one earns the remaining {round(bn_max - bn_earned_r, 1)} points."
        )
    business_item = {
        "label": "Business Name", "formula": f"step {bn_source}", "evidence_note": bn_note,
        "earned": bn_earned_r, "max": bn_max,
        "evidence": {"business_name": business_name.get("value"), "source": bn_source},
    }

    gl_scale = scales.get("glossary", {}) or {}
    term_status_scale = gl_scale.get("term_status", {}) or {}
    if glossary.get("linked"):
        term_status = glossary.get("term_status", "draft")
        gl_earned = float(gl_scale.get("linked", 3) + term_status_scale.get(term_status, 0))
        gl_formula = f"{gl_scale.get('linked', 3)} + {term_status_scale.get(term_status, 0)} ({term_status})"
    else:
        gl_earned = 0.0
        gl_formula = "unlinked → 0"
    gl_earned_r = _round(gl_earned, 1)
    if glossary.get("linked"):
        gl_note = (
            f"linked to a glossary term ('{glossary.get('term_status', 'draft')}' status) "
            f"→ {_note_tail(gl_earned_r, gl_max)}."
        )
    else:
        gl_note = f"not linked to a glossary term → 0/{gl_max}; linking one earns up to {gl_max} points."
    glossary_item = {
        "label": "Glossary Linkage", "formula": gl_formula, "evidence_note": gl_note,
        "earned": gl_earned_r, "max": gl_max,
        "evidence": {"linked": bool(glossary.get("linked")), "term_status": glossary.get("term_status")},
    }

    semantic_item = _semantic_line_item(semantic_record, config.semantic_line_item_max, config)

    line_items = [definition_item, business_item, glossary_item, semantic_item]
    earned = _round(sum(li["earned"] for li in line_items), 1)
    base_max = float(config.component_weights.get("interpretation", 30))
    return {"name": "interpretation", "earned": earned, "base_max": base_max, "line_items": line_items}


# ── Reference Data component (§4.3) ──────────────────────────────────────────

def _score_reference_data(reference_data: dict | None, col_dict: ColumnDict,
                         config: DQScoringConfig) -> dict:
    scales = config.reference_data_scales or {}
    reference_data = reference_data or {}
    codes_documented_max = float(scales.get("codes_documented_max", 12))
    status_scale = scales.get("status", {}) or {}

    distinct_count = reference_data.get("distinct_count")
    if distinct_count is None:
        distinct_count = col_dict.get("distinct_count") or 0
    codes_documented = reference_data.get("codes_documented", 0) or 0
    if distinct_count:
        codes_earned = _round(codes_documented_max * codes_documented / distinct_count, 1)
    else:
        codes_earned = _round(codes_documented_max, 1)
    if distinct_count:
        codes_note = (
            f"{codes_documented} of {distinct_count} codes documented "
            f"→ {_note_tail(codes_earned, codes_documented_max)}."
        )
    else:
        codes_note = f"no distinct codes captured yet → {_note_tail(codes_earned, codes_documented_max)}."
    codes_item = {
        "label": "Codes documented",
        "formula": f"{codes_documented_max} × {codes_documented}/{distinct_count}",
        "evidence_note": codes_note,
        "earned": codes_earned, "max": codes_documented_max,
        "evidence": {"codes_documented": codes_documented, "distinct_count": distinct_count},
    }

    status = reference_data.get("status", "none") or "none"
    status_earned = _round(float(status_scale.get(status, 0)), 1)
    status_max = float(status_scale.get("approved", 8))
    if status == "approved":
        status_note = f"code set is approved → {_note_tail(status_earned, status_max)}."
    elif status == "none":
        status_note = (
            f"code set not yet submitted for approval → {status_earned}/{status_max}; "
            f"approving it earns up to {status_max} points."
        )
    else:
        status_note = (
            f"code set status is '{status}' → {status_earned}/{status_max}; "
            f"approving it earns the remaining {round(status_max - status_earned, 1)} points."
        )
    status_item = {
        "label": "Code set approved", "formula": f"step {status}", "evidence_note": status_note,
        "earned": status_earned,
        "max": status_max, "evidence": {"refdata_status": status},
    }

    line_items = [codes_item, status_item]
    earned = _round(sum(li["earned"] for li in line_items), 1)
    return {"name": "reference_data", "earned": earned, "base_max": 20.0, "line_items": line_items}


# ── validator yardstick (F2 / §10.2) ─────────────────────────────────────────

def _validator_yardstick(semantic_record: dict | None, col_dict: ColumnDict,
                        config: DQScoringConfig) -> float | None:
    """Return the confirmed validator pass rate when it should drive Validity.

    Fires only for a steward-confirmed, validator-backed semantic type whose
    validator the profiler actually scored (``validator_pass_rates``).
    """
    type_id = accepted_semantic_type(semantic_record)
    if not type_id or type_id not in set(config.validator_backed_semantic_types or []):
        return None
    rates = col_dict.get("validator_pass_rates")
    if not isinstance(rates, dict) or not rates:
        return None
    if type_id in rates:
        value = rates[type_id]
    else:
        value = max(rates.values())
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Semantic Type line-item (folded into Interpretation · SD-R3c · F3) ───────

def _semantic_line_item(semantic_record: dict | None, max_points: float, config: DQScoringConfig) -> dict:
    """Build the Semantic Type line-item inside Interpretation (SD-R3c).

    Folded in from the retired 4th 'semantic' component (U6a/U6b): the scoring
    logic is unchanged — the governance disposition earns a config fraction of the
    line-item max (accepted full / high-confidence candidate partial / low-confidence
    candidate low / unresolved 0), minus a ``type_value_conflict`` deduction, floored
    at 0 — only where its points live changed. Reads the F3 contract fields off the
    injected semantic record; never resolver internals. When no resolver record
    exists the line-item scores 0/max (unresolved), just like an unresolved type.

    2026-08-20 (tech-debt #13/#36/#45): there is no persisted disposition word anymore
    — the bucket is derived directly from ``type_id``/``accepted_at``/``confidence``
    against the resolver's own ``floor_threshold``, instead of reading a stale
    ``proposed``/``suggested``/``confirmed`` string. The earned POINTS are unchanged.
    """
    scale = config.semantic_line_item_scale or {}
    conflict_frac = config.semantic_type_conflict_deduction
    rec = semantic_record or {}
    type_id = rec.get("type_id")
    if not type_id or type_id == "unresolved":
        scale_key = "unresolved"
    elif rec.get("accepted_at"):
        scale_key = "accepted"
    else:
        confidence = float(rec.get("confidence") or 0.0)
        scale_key = "proposed" if confidence >= DEFAULT_FLOOR_THRESHOLD else "suggested"
    frac = float(scale.get(scale_key, 0.0))
    conflict = bool(rec.get("type_value_conflict"))
    deduction = max_points * conflict_frac if conflict else 0.0
    earned = _round(max(0.0, max_points * frac - deduction), 1)
    max_r = _round(max_points, 1)
    full = _round(max_points * float(scale.get("accepted", 1.0)), 1)
    remaining = round(full - earned, 1)
    deduction_r = round(deduction, 1)

    if scale_key == "accepted":
        base = f"semantic type accepted → {_note_tail(earned, max_r)}"
    elif scale_key == "proposed":
        base = (f"semantic type proposed, not yet accepted → {earned}/{max_r}; "
                f"accepting it earns the remaining {remaining} points")
    elif scale_key == "suggested":
        base = (f"semantic type suggested (weak guess) → {earned}/{max_r}; "
                f"accepting it earns the remaining {remaining} points")
    else:
        base = (f"no semantic type resolved → {earned}/{max_r}; "
                f"resolving and accepting one earns up to {full} points")
    if conflict:
        base += f"; a type/value conflict deducts {deduction_r}"
    note = base + "."

    formula = f"{max_r} × {frac}" + (f" − {deduction_r}" if conflict else "")
    return {
        "label": "Semantic Type",
        "validation": "semantic type acceptance (F3)",
        "formula": formula,
        "evidence_note": note,
        "earned": earned,
        "max": max_r,
        "evidence": {
            "accepted": bool(rec.get("accepted_at")), "type_id": type_id, "tier": rec.get("tier"),
            "source": rec.get("source"), "type_value_conflict": conflict,
        },
        "findings": [],
    }


# ── orchestrator ─────────────────────────────────────────────────────────────
def score_column(
    *,
    col_dict: ColumnDict,
    tbl_dict: dict | None = None,
    semantic_record: dict | None = None,
    definition: dict | None = None,
    business_name: dict | None = None,
    glossary: dict | None = None,
    reference_data: dict | None = None,
    intent: dict | None = None,
    findings: list | None = None,
    assessment_scope: str = "in_scope",
    config: DQScoringConfig,
) -> dict[str, Any]:
    """Score one column and return the §9-shaped breakdown record.

    Out-of-scope columns (D1) and empty tables (§16.6) return an ``unscored``
    record with no components and no grade — excluded from scoring entirely.
    """
    if assessment_scope == "out_of_scope":
        return {"state": "unscored", "reason": "out_of_scope",
                "model_version": config.model_version, "breakdown_version": BREAKDOWN_VERSION}
    if (col_dict.get("row_count") or 0) == 0:
        return {"state": "unscored", "reason": "empty",
                "model_version": config.model_version, "breakdown_version": BREAKDOWN_VERSION}

    archetype, archetype_reason = detect_archetype(col_dict, tbl_dict, semantic_record, config)
    resolved_intent = _resolve_intent(intent, config)
    validator_yardstick = _validator_yardstick(semantic_record, col_dict, config)

    profile = _score_profile(archetype, col_dict, resolved_intent, findings or [],
                             validator_yardstick, config)
    interpretation_component = _score_interpretation(
        definition, business_name, glossary, semantic_record, config
    )

    components = [profile, interpretation_component]
    if archetype == "coded":
        components.append(_score_reference_data(reference_data, col_dict, config))

    # Reallocation (§6): scale applicable component maxima up to Σ = 100.
    sum_base = sum(c["base_max"] for c in components)
    factor = Decimal(100) / Decimal(str(sum_base)) if sum_base else Decimal(1)
    scaled_sum = Decimal(0)
    for c in components:
        scaled_max = _q(Decimal(str(c["base_max"])) * factor, 2)
        scaled_earned = _q(Decimal(str(c["earned"])) * factor, 2)
        c["scaled_max"] = float(scaled_max)
        c["scaled_earned"] = float(scaled_earned)
        c["grade"] = _tab_grade(c["earned"], c["base_max"], config)
        scaled_sum += scaled_earned

    dq_score = _round_int(scaled_sum)
    grade = grade_for(dq_score, config)

    # Secondary data · governance split (§16.8) — both already in the breakdown.
    data_earned = profile["earned"]
    data_score = _round_int(100 * data_earned / profile["base_max"]) if profile["base_max"] else 0
    gov_components = [c for c in components if c["name"] != "profile"]
    gov_base = sum(c["base_max"] for c in gov_components)
    gov_earned = sum(c["earned"] for c in gov_components)
    governance_score = _round_int(100 * gov_earned / gov_base) if gov_base else 0

    record = {
        "state": "scored",
        "dq_score": dq_score,
        "grade_label": grade["label"],
        "grade_color_intent": grade["color_intent"],
        "model_version": config.model_version,
        "breakdown_version": BREAKDOWN_VERSION,
        "archetype": archetype,
        "archetype_reason": archetype_reason,
        "applicable_components": [c["name"] for c in components],
        "reallocation_factor": float(_q(factor, 6)),
        "data_score": data_score,
        "governance_score": governance_score,
        "components": components,
    }

    # Remediation layer (§17) — derived from the line-item gaps above, never a
    # re-score. Persisted alongside the breakdown (mirrors ``evidence_note``).
    actions = derive_actions(record, config)
    record["actions"] = actions
    record["path_to_next_grade"] = path_to_next_grade(record, actions, config)
    record["inapplicable_components"] = inapplicable_components(record, config)
    return record
