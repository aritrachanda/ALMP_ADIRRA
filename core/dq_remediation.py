"""DQ remediation layer — from score to action (DQ §17), pure & derived.

A score that only says *how bad* is half a product; the data owner needs
*what now*. Because every lost point already traces to a named line-item with
cited evidence (§9), remediation is a **derivation, not a new subsystem**: any
line-item where ``earned < max`` generates an improvement action whose
``points`` is exactly that line-item's gap, scaled by the reallocation factor
so it reads on the same composite 0–100 scale as the badge.

Nothing here re-scores. Actions are derived from the breakdown the scorer
already produced, so the slab can never contradict the score (§17 constraint).
Mirrors the ``evidence_note`` pattern: computed in the scorer, persisted on the
record, healed on a ``BREAKDOWN_VERSION`` bump.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from core.dq_config import DQScoringConfig

# A line-item gap smaller than this (after rounding to 1 dp) yields no action —
# a full or effectively-full line-item is nothing to fix.
_MIN_GAP = 0.05

# Which line-items are fixable inside ADIRRA (``governance``) versus at the data
# source (``data``) — the operationally important split of §17.1.
_GOVERNANCE_LINE_ITEMS = {
    "Definition", "Business Name", "Glossary Linkage",
    "Codes documented", "Code set approved", "Semantic Type",
}


def _action_step(label: str, evidence: dict[str, Any] | None) -> tuple[str, str]:
    """Plain-language, GAP-AWARE step for a line-item + its ``action_type``.

    Gap-aware means the wording reflects the line-item's *current* state, so we
    never tell a steward to do something already done (§17 constraint; e.g. an
    already-linked glossary term is advanced, not "linked"). Text uses the same
    plain vocabulary as the Profile / Definition tabs — no jargon (Task 4).
    """
    ev = evidence or {}
    action_type = "governance" if label in _GOVERNANCE_LINE_ITEMS else "data"

    # ── data-side (fix at source) ───────────────────────────────────────────
    if label == "Completeness":
        return (
            "Some values are missing — blanks, empty text or placeholder entries "
            "like UNKNOWN or 9999. Fill them in at source, or mark the column "
            "optional if the gaps are expected.",
            action_type,
        )
    if label == "Validity":
        return (
            "Some values don't match the shape this column should have. Correct the "
            "odd values at source, or confirm the expected format is right.",
            action_type,
        )
    if label == "Uniqueness":
        return (
            "Some key values are repeated when each should be one-of-a-kind. "
            "Resolve the duplicates so the key is genuinely unique.",
            action_type,
        )
    if label == "Consistency":
        # Polish Batch Task 3 — name the actual signal when the deduction is an
        # outlier penalty, instead of the generic "some values look unusual".
        # Falls back to the generic wording for the other Consistency deductions
        # (single-constant, constant-run, dominance) — unchanged, still tested.
        deductions = ev.get("deductions") or []
        outlier = next((d for d in deductions if d.get("name") == "outlier_penalty"), None)
        if outlier is not None:
            count = ev.get("numeric_outlier_count")
            avg = ev.get("numeric_avg")
            stddev = ev.get("numeric_stddev")
            plural = "value" if count == 1 else "values"
            if count and avg is not None and stddev is not None:
                lower = avg - 3 * stddev
                upper = avg + 3 * stddev
                return (
                    f"{count} {plural} sit far outside the typical range for this column "
                    f"(beyond mean ± 3σ ≈ {lower:,.0f}–{upper:,.0f}). Check whether "
                    f"they're genuine or data errors.",
                    action_type,
                )
            # Outlier count known but not the mean/stddev to bound a range — say
            # what IS available; the exact value(s) would need a profiler field
            # this scorer doesn't have (do not invent it).
            return (
                f"{count or 'Some'} {plural} sit beyond the normal 3σ range for this "
                f"column. Check whether they're genuine or data errors.",
                action_type,
            )
        return (
            "Some values look unusual — a few sit far outside the normal range for "
            "this column, or a single value dominates. Check whether they're "
            "genuine or data errors.",
            action_type,
        )
    if label == "Findings overlay":
        return (
            "There are open data-quality observations on this column that aren't "
            "covered elsewhere. Review and resolve them.",
            action_type,
        )

    # ── governance-side (fixable inside ADIRRA), all gap-aware ──────────────────
    if label == "Definition":
        if ev.get("present"):
            if ev.get("is_ai"):
                return (
                    "A description exists but it was AI-drafted and not yet reviewed. "
                    "Check it over and mark it steward-approved.",
                    action_type,
                )
            return ("Advance this column's description to approved.", action_type)
        return ("Write a short business-friendly description for this column.", action_type)

    if label == "Business Name":
        source = ev.get("source")
        if source and source != "none":
            return (
                "A business name exists but it was auto-generated. Confirm a "
                "steward-chosen business name for this column.",
                action_type,
            )
        return ("Give this column a plain-English business name.", action_type)

    if label == "Glossary Linkage":
        if ev.get("linked"):
            status = ev.get("term_status") or "draft"
            if status != "published":
                return (
                    f"This column is already linked to a glossary term, but that term "
                    f"is only '{status}'. Advance the term to Published to earn the "
                    f"last point.",
                    action_type,
                )
            # linked + published is full (10/10) → no gap reaches here; safe fallback.
            return ("Review the linked glossary term.", action_type)
        return ("Link this column to a glossary term.", action_type)

    if label == "Codes documented":
        documented = ev.get("codes_documented")
        distinct = ev.get("distinct_count")
        if documented is not None and distinct:
            remaining = max(0, int(distinct) - int(documented))
            plural = "" if remaining == 1 else "s"
            return (
                f"{remaining} of this column's codes have no meaning recorded. Add a "
                f"meaning for each on the Reference Data tab.",
                action_type,
            ) if remaining else (
                "Document the meaning of each undocumented code on the Reference Data tab.",
                action_type,
            )
        return (
            "Document the meaning of each undocumented code on the Reference Data tab.",
            action_type,
        )

    if label == "Code set approved":
        status = ev.get("refdata_status") or "none"
        if status not in ("none", None):
            return (
                f"The code set is '{status}'. Advance it to approved on the Reference "
                f"Data tab.",
                action_type,
            )
        return ("Submit the code set for approval on the Reference Data tab.", action_type)

    if label == "Semantic Type":
        # SD-R3c — the recovery path for a Semantic Type line-item gap inside
        # Interpretation. Gap-aware: a proposed/suggested type is *accepted*; an
        # unresolved/rejected one is *resolved then accepted*. A type/value
        # conflict is called out too.
        state = str(ev.get("state") or "unresolved")
        type_id = ev.get("type_id")
        conflict = bool(ev.get("type_value_conflict"))
        if type_id and type_id != "unresolved" and state in ("proposed", "suggested"):
            base = (
                "A semantic type is suggested for this column but not yet accepted. "
                "Accept it on the Interpretation tab."
            )
        else:
            base = (
                "No semantic type is resolved for this column. Resolve and accept one "
                "on the Interpretation tab."
            )
        if conflict:
            base += (
                " There is also a type/value conflict — check the values match the "
                "declared type before confirming."
            )
        return (base, action_type)

    return (f"Improve {label}.", action_type)


def _round1(value: Any) -> float:
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _grade_for(score: float, config: DQScoringConfig) -> str | None:
    """Band label for a score — a local lookup (§7) to avoid importing the
    scorer (which imports this module). First descending band whose ``min`` the
    score meets."""
    bands = config.grade_bands or []
    for band in bands:
        if score >= band.get("min", 0):
            return band.get("label")
    return bands[-1].get("label") if bands else None


def derive_actions(record: dict[str, Any], config: DQScoringConfig) -> list[dict[str, Any]]:
    """Derive the ordered improvement-action list from a scored breakdown (§17).

    One action per line-item whose ``earned < max``; ``points`` is that gap
    (``max − earned``) scaled by the record's ``reallocation_factor`` so it is
    expressed on the composite scale. A full line-item yields no action —
    actions are *derived*, never invented. Sorted by impact (largest point-gain
    first); ties keep component/line-item order (a stable sort).
    """
    if record.get("state") != "scored":
        return []
    factor = Decimal(str(record.get("reallocation_factor", 1.0) or 1.0))
    base_score = record.get("dq_score")

    actions: list[dict[str, Any]] = []
    for component in record.get("components", []) or []:
        comp_name = component.get("name")
        for li in component.get("line_items", []) or []:
            gap = float(li.get("max", 0)) - float(li.get("earned", 0))
            if gap <= 0:
                continue
            points = _round1(Decimal(str(gap)) * factor)
            if points < _MIN_GAP:
                continue
            label = li.get("label", "")
            step, action_type = _action_step(label, li.get("evidence"))
            action: dict[str, Any] = {
                "component": comp_name,
                "line_item": label,
                "step": step,
                "action_type": action_type,
                "points": points,
                "evidence_note": li.get("evidence_note"),
            }
            # Destination, not a bare delta (§17.2, Task 2): where taking this one
            # action lands the column's composite score, and the grade there.
            if base_score is not None:
                resulting = _round1(Decimal(str(base_score)) + Decimal(str(points)))
                action["resulting_score"] = resulting
                action["resulting_grade"] = _grade_for(resulting, config)
            actions.append(action)

    # Stable sort by descending points — equal-impact actions keep the natural
    # component/line-item order they were emitted in (Codes documented before
    # Code set approved, etc.), matching the §17.2 worked path.
    actions.sort(key=lambda a: a["points"], reverse=True)
    return actions


def path_to_next_grade(
    record: dict[str, Any], actions: list[dict[str, Any]], config: DQScoringConfig
) -> dict[str, Any] | None:
    """Minimal set of actions that crosses into the next grade band (§17.2).

    Greedily takes the highest-impact actions until their recoverable points
    reach the next band's threshold. Returns ``None`` for an un-scored column;
    an ``at_top_band`` payload when the column is already in the top band.
    """
    if record.get("state") != "scored":
        return None
    score = record.get("dq_score")
    if score is None:
        return None

    current_grade = record.get("grade_label")
    bands = config.grade_bands or []
    # Next band = the smallest ``min`` strictly above the current score.
    higher = sorted((b for b in bands if b.get("min", 0) > score), key=lambda b: b["min"])
    if not higher:
        return {
            "at_top_band": True,
            "current_score": score,
            "current_grade": current_grade,
            "next_grade": None,
            "next_grade_min": None,
            "points_needed": 0.0,
            "landing_score": score,
            "landing_grade": current_grade,
            "actions": [],
            "reachable": True,
            "any_one_suffices": False,
        }

    next_band = higher[0]
    next_min = next_band["min"]
    points_needed = _round1(next_min - score)

    chosen: list[dict[str, Any]] = []
    cumulative = 0.0
    for action in actions:  # already sorted by impact
        chosen.append(action)
        cumulative = _round1(cumulative + action["points"])
        if cumulative >= points_needed:
            break

    # The REAL destination — where these actions actually land the score — not
    # the band threshold (Task 2). Cumulative can overshoot the next band.
    landing_score = _round1(score + cumulative)
    landing_grade = _grade_for(landing_score, config)

    # Polish Batch Task 4 — when the single action that closed the gap has
    # other candidates of EXACTLY equal impact, any one of them would have
    # closed it too (the greedy pick is otherwise arbitrary among ties). Flag
    # that so the UI can say "any one of these" instead of implying this
    # specific action is the only route. Only meaningful for a single pivotal
    # action — once two-or-more actions are genuinely required together, they
    # are no longer interchangeable and the flag stays False.
    any_one_suffices = False
    if len(chosen) == 1:
        pivot_points = chosen[0]["points"]
        ties = [
            a for a in actions
            if a is not chosen[0] and abs(a["points"] - pivot_points) < 1e-9
        ]
        if ties:
            any_one_suffices = True
            chosen = [chosen[0]] + ties

    return {
        "at_top_band": False,
        "current_score": score,
        "current_grade": current_grade,
        "next_grade": next_band.get("label"),
        "next_grade_min": next_min,
        "points_needed": points_needed,
        "landing_score": landing_score,
        "landing_grade": landing_grade,
        "actions": chosen,
        "reachable": cumulative >= points_needed,
        "any_one_suffices": any_one_suffices,
    }


def inapplicable_components(record: dict[str, Any], config: DQScoringConfig) -> list[str]:
    """Configured components that did not apply to this column (for §6 legibility).

    Every weighted component minus the ones that scored — e.g. ``reference_data``
    on a non-coded column. Names only; the frontend renders the sentence.
    """
    if record.get("state") != "scored":
        return []
    applicable = set(record.get("applicable_components") or [])
    enabled = list((config.component_weights or {}).keys())
    return [name for name in enabled if name not in applicable]
