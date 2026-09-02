"""DQ dataset roll-up scorer — pure, deterministic, hand-recalculable.

Implements the dataset-level roll-up of DQ-Scoring-Model-Design-v1.md §15: a
table's in-scope column scores aggregate into one dataset composite on the
SAME 0–100 scale and the SAME grade bands as the column scorer — no new math
families, no new band scheme. Two components:

  * ``column_rollup``    (base 85) — weighted mean of the columns' DQ scores.
  * ``dataset_integrity`` (base 15) — table-level defects no single column owns
                                     (duplicate PK rows, orphan FKs), chosen via
                                     an integrity *profile* the same way column
                                     archetypes pick their dimensions.

The §6 reallocation rule is reused unchanged: when dataset_integrity is not
applicable (no keys to check) its weight redistributes and the dataset is never
penalised for it.

Rounding law (§5) is shared verbatim with the column scorer — the helpers are
imported from ``core.dq_scorer`` so line-items round to 1 dp, scaled components
to 2 dp, and the overall score is the single integer rounding. This keeps the
two scorers on one rounding law (ROUND_HALF_UP everywhere).

Aggregates *persisted column records* (§16.4) — it never re-profiles. The
service passes in each column's latest score; this module only does arithmetic.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from core.dq_config import DQScoringConfig
from core.dq_scorer import _q, _round, _round_int, grade_for

# Shape version of the emitted dataset breakdown — the store/service use it as
# an extra cache-invalidation key (heal-on-read) exactly like the column
# scorer's ``BREAKDOWN_VERSION`` (DQ §16.3–16.4).
DATASET_BREAKDOWN_VERSION = 1


def _clamp01_dec(x: Decimal) -> Decimal:
    if x < 0:
        return Decimal(0)
    if x > 1:
        return Decimal(1)
    return x


def _tab_grade(earned: float, max_d: float, config: DQScoringConfig) -> dict[str, Any]:
    if not max_d:
        return {"label": None, "color_intent": None}
    return grade_for(_round_int(100 * earned / max_d), config)


def _integrity_profile(pk_applies: bool, fk_applies: bool) -> str | None:
    if pk_applies and fk_applies:
        return "pk_and_fk"
    if pk_applies:
        return "pk_only"
    if fk_applies:
        return "fk_only"
    return None


def _score_column_rollup(scored: list[dict], rollup_max: float, weighting: str,
                         crit_mult: dict[str, float]) -> dict[str, Any]:
    """§15.1 — weighted mean of the columns' DQ scores, scaled to ``rollup_max``.

    ``contribution`` is each column's share of the 0–100 mean (``w·DQ/Σw``) so
    the contributions sum to the mean and the whole roll-up is hand-checkable.
    """
    def _weight(c: dict) -> float:
        if weighting == "criticality":
            return float(crit_mult.get(c.get("criticality") or "standard", 1.0))
        return 1.0

    sum_w = Decimal(0)
    weighted_sum = Decimal(0)
    line_items: list[dict[str, Any]] = []
    for c in scored:
        w = _weight(c)
        dq = int(c["dq_score"])
        w_dec = Decimal(str(w))
        sum_w += w_dec
        weighted_sum += w_dec * Decimal(dq)

    for c in scored:
        w = _weight(c)
        dq = int(c["dq_score"])
        contribution = _round(Decimal(str(w)) * Decimal(dq) / sum_w, 2) if sum_w else 0.0
        line_items.append({
            "key": c["column"], "dq_score": dq, "weight": w, "contribution": contribution,
            # Element-level lingo carried onto the roll-up row (grade + how
            # many improvement actions remain), so the UI reads the same way
            # at both levels — additive, no existing consumer keys change.
            "grade_label": c.get("grade_label"),
            "grade_color_intent": c.get("grade_color_intent"),
            "action_count": c.get("action_count", 0),
        })

    mean = weighted_sum / sum_w if sum_w else Decimal(0)
    earned = _round(Decimal(str(rollup_max)) * mean / Decimal(100), 1)
    # Contribution breakdown: which columns dragged the roll-up down (lowest first).
    line_items.sort(key=lambda li: li["dq_score"])
    return {
        "name": "column_rollup",
        "earned": earned,
        "base_max": float(rollup_max),
        "column_count": len(scored),
        "mean_score": _round(mean, 1),
        "line_items": line_items,
    }


def _score_dataset_integrity(profile_name: str, table_signals: dict, integrity_max: float,
                             config: DQScoringConfig) -> dict[str, Any]:
    """§15.2 — table-level PK-uniqueness / referential-integrity defects."""
    ds_cfg = config.dataset_scoring or {}
    profiles = ds_cfg.get("integrity_profiles", {}) or {}
    profile_maxima = profiles.get(profile_name, {}) or {}
    itol = ds_cfg.get("integrity_tolerances", {}) or {}
    row_count = table_signals.get("row_count") or 0

    line_items: list[dict[str, Any]] = []
    if "pk_uniqueness" in profile_maxima:
        pk_max = float(profile_maxima["pk_uniqueness"])
        zero_at = Decimal(str(itol.get("pk_duplicates_zero_at", 0.02)))
        dup = table_signals.get("duplicate_count") or 0
        dup_rate = Decimal(dup) / Decimal(row_count) if row_count else Decimal(0)
        factor = _clamp01_dec(Decimal(1) - (dup_rate / zero_at if zero_at else Decimal(0)))
        earned = _round(Decimal(str(pk_max)) * factor, 1)
        pct = round(float(dup_rate) * 100, 3)
        line_items.append({
            "label": "PK uniqueness",
            "formula": f"{pk_max} × (1 − {float(dup_rate)}/{float(zero_at)})",
            "evidence_note": f"{pct}% of rows share a primary-key value → {earned}/{pk_max}.",
            "earned": earned, "max": pk_max,
            "evidence": {"duplicate_count": dup, "row_count": row_count},
        })
    if "referential_integrity" in profile_maxima:
        ri_max = float(profile_maxima["referential_integrity"])
        zero_at = Decimal(str(itol.get("orphan_fk_zero_at", 0.05)))
        orphan = table_signals.get("orphan_fk_count") or 0
        orphan_rate = Decimal(orphan) / Decimal(row_count) if row_count else Decimal(0)
        factor = _clamp01_dec(Decimal(1) - (orphan_rate / zero_at if zero_at else Decimal(0)))
        earned = _round(Decimal(str(ri_max)) * factor, 1)
        pct = round(float(orphan_rate) * 100, 3)
        line_items.append({
            "label": "Referential integrity",
            "formula": f"{ri_max} × (1 − {float(orphan_rate)}/{float(zero_at)})",
            "evidence_note": f"{pct}% of rows have an orphan foreign key → {earned}/{ri_max}.",
            "earned": earned, "max": ri_max,
            "evidence": {"orphan_fk_count": orphan, "row_count": row_count},
        })

    earned = _round(sum(li["earned"] for li in line_items), 1)
    return {
        "name": "dataset_integrity",
        "earned": earned,
        "base_max": float(integrity_max),
        "profile": profile_name,
        "line_items": line_items,
    }


def score_dataset(
    *,
    columns: list[dict[str, Any]],
    table_signals: dict[str, Any],
    config: DQScoringConfig,
) -> dict[str, Any]:
    """Roll up a table's column scores into one dataset DQ record (§15).

    *columns* — one entry per column: ``{column, state, dq_score, archetype,
    criticality, in_scope}``. *table_signals* — ``{row_count, duplicate_count,
    orphan_fk_count, primary_key, has_fk}``.

    Scope-aware (D1): out-of-scope columns are excluded from the roll-up weight;
    a table whose columns are ALL out of scope returns an ``unscored`` record
    with ``reason: fully_descoped`` (extends §16.6). A table with in-scope
    columns but no scored ones (e.g. all empty) returns ``no_scored_columns``.
    """
    ds_cfg = config.dataset_scoring or {}
    weights = ds_cfg.get("component_weights", {}) or {}
    rollup_max = float(weights.get("column_rollup", 85))
    integrity_max = float(weights.get("dataset_integrity", 15))
    weighting = ds_cfg.get("column_weighting", "equal")
    crit_mult = ds_cfg.get("criticality_multipliers", {}) or {}

    in_scope = [c for c in columns if c.get("in_scope", True)]
    if columns and not in_scope:
        return {
            "state": "unscored", "reason": "fully_descoped",
            "model_version": config.model_version,
            "breakdown_version": DATASET_BREAKDOWN_VERSION,
        }

    scored = [c for c in in_scope
              if c.get("state") == "scored" and c.get("dq_score") is not None]
    if not scored:
        return {
            "state": "unscored", "reason": "no_scored_columns",
            "model_version": config.model_version,
            "breakdown_version": DATASET_BREAKDOWN_VERSION,
        }

    rollup = _score_column_rollup(scored, rollup_max, weighting, crit_mult)

    # Integrity profile — deterministic, with the §15.2 no-double-counting rules.
    pk = list(table_signals.get("primary_key") or [])
    pk_applies = False
    if pk:
        if len(pk) > 1:
            pk_applies = True  # composite PK — no single column prices it
        else:
            # single-column PK already prices its duplicates in that column's
            # Uniqueness dimension when the column is key_like — dataset PK N/A.
            arche = next((c.get("archetype") for c in scored if c["column"] == pk[0]), None)
            pk_applies = arche != "key_like"
    fk_applies = bool(table_signals.get("has_fk"))
    profile_name = _integrity_profile(pk_applies, fk_applies)

    components: list[dict[str, Any]] = [rollup]
    if profile_name:
        components.append(_score_dataset_integrity(profile_name, table_signals, integrity_max, config))

    # Reallocation (§6): scale applicable component maxima up to Σ = 100.
    sum_base = sum(c["base_max"] for c in components)
    factor = Decimal(100) / Decimal(str(sum_base)) if sum_base else Decimal(1)
    scaled_sum = Decimal(0)
    for c in components:
        scaled_earned = _q(Decimal(str(c["earned"])) * factor, 2)
        c["scaled_max"] = float(_q(Decimal(str(c["base_max"])) * factor, 2))
        c["scaled_earned"] = float(scaled_earned)
        c["grade"] = _tab_grade(c["earned"], c["base_max"], config)
        scaled_sum += scaled_earned

    dq_score = _round_int(scaled_sum)
    grade = grade_for(dq_score, config)

    return {
        "state": "scored",
        "dq_score": dq_score,
        "grade_label": grade["label"],
        "grade_color_intent": grade["color_intent"],
        "model_version": config.model_version,
        "breakdown_version": DATASET_BREAKDOWN_VERSION,
        "applicable_components": [c["name"] for c in components],
        "integrity_profile": profile_name,
        "reallocation_factor": float(_q(factor, 6)),
        "column_count": len(scored),
        "components": components,
    }
