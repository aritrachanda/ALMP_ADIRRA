"""Phase 5a — migrate the element-lifecycle slice of ``element_states.yaml`` into Postgres.

Reads the YAML store (states + submission overlay + description/business-name presence),
derives the canonical Phase-5 status for each element (``core.lifecycle.derive_status``),
and loads it into ``review_subject`` / ``review_task`` / ``lifecycle_transition``.

Value-preserving w.r.t. DQ scoring — the ONLY intended lifecycle-points movements are
draft-with-content → draft (1→2) and submitted-undecided → in_review (2→3). Everything else
is neutral. ``lifecycle_points_summary`` produces the before/after evidence for the report.

Descriptions / business names / data stories / assessment scope stay in YAML (a later
slice). Idempotent: ``force=True`` truncates the element rows first.

CLI:  python -m core.element_lifecycle_migrate [--force] [--yaml PATH]
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, func, select

from core import lifecycle as lc
from core.glossary_db.db import session_scope
from core.shared.models import LifecycleTransition, ReviewSubject, ReviewTask
from core.element_lifecycle_repo import SUBJECT_TYPE, TASK_TYPE

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_YAML = _ROOT / "governance" / "element_states.yaml"

#: The pre-Phase-5 Definition lifecycle scale (baseline for the parity summary).
OLD_LIFECYCLE_SCALE = {"approved": 5, "defined": 2, "draft": 1}


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _load(yaml_path: Path) -> dict:
    if not yaml_path.exists():
        return {}
    with yaml_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _relevant_keys(data: dict) -> set[str]:
    states = data.get("states", {}) or {}
    descriptions = data.get("descriptions", {}) or {}
    business_names = data.get("business_names", {}) or {}
    overlay = data.get("submission_overlay", {}) or {}
    keys = set(states) | set(overlay)
    keys |= {k for k, v in descriptions.items() if v}
    keys |= {k for k, v in business_names.items() if v}
    return keys


def _derive(data: dict, key: str) -> tuple[str, bool]:
    """Return (derived_status, has_content) for one element key."""
    states = data.get("states", {}) or {}
    descriptions = data.get("descriptions", {}) or {}
    business_names = data.get("business_names", {}) or {}
    overlay = data.get("submission_overlay", {}) or {}
    old_state = states.get(key)
    has_content = bool(descriptions.get(key)) or bool(business_names.get(key))
    ov = overlay.get(key) or {}
    derived = lc.derive_status(
        old_state=old_state,
        has_content=has_content,
        submitted=bool(ov.get("submitted_at")),
        decision=ov.get("decision"),
    )
    return derived, has_content


def lifecycle_points_summary(*, yaml_path: Path | str = _DEFAULT_YAML,
                             new_scale: dict[str, float]) -> list[dict[str, Any]]:
    """Per-element old vs new Definition-lifecycle points (the parity evidence).

    ``old_pts``/``new_pts`` count the lifecycle bonus only when a description is present
    (the scorer applies it only when ``present`` is true), so this mirrors the real
    Definition line-item contribution exactly.
    """
    data = _load(Path(yaml_path))
    descriptions = data.get("descriptions", {}) or {}
    states = data.get("states", {}) or {}
    rows: list[dict[str, Any]] = []
    for key in sorted(_relevant_keys(data)):
        derived, has_content = _derive(data, key)
        present = bool(descriptions.get(key))
        old_state = states.get(key) or "draft"
        old_pts = OLD_LIFECYCLE_SCALE.get(old_state, 0) if present else 0
        new_pts = float(new_scale.get(derived, 0)) if present else 0
        rows.append({
            "key": key, "old_state": old_state, "derived": derived,
            "present": present, "old_pts": old_pts, "new_pts": new_pts,
            "delta": new_pts - old_pts,
        })
    return rows


def migrate_element_states(*, yaml_path: Path | str = _DEFAULT_YAML,
                           dsn: str | None = None, force: bool = False) -> dict[str, Any]:
    """Load the derived element statuses into Postgres. Returns a stats dict."""
    data = _load(Path(yaml_path))
    overlay = data.get("submission_overlay", {}) or {}
    keys = _relevant_keys(data)

    stats: dict[str, Any] = {"total_keys": len(keys), "written": 0,
                             "skipped_empty": 0, "by_status": {}}

    with session_scope(dsn) as s:
        if force:
            ids = s.execute(
                select(ReviewSubject.id).where(ReviewSubject.subject_type == SUBJECT_TYPE)
            ).scalars().all()
            if ids:
                s.execute(delete(ReviewTask).where(ReviewTask.review_subject_id.in_(ids)))
            s.execute(delete(ReviewSubject).where(ReviewSubject.subject_type == SUBJECT_TYPE))
            s.execute(delete(LifecycleTransition).where(
                LifecycleTransition.subject_type == SUBJECT_TYPE))

        for key in sorted(keys):
            derived, has_content = _derive(data, key)
            # An 'empty' shell (no content, default state) is the repo default —
            # skip it to keep the table lean and identical to a fresh read.
            if derived == "empty":
                stats["skipped_empty"] += 1
                continue

            ov = overlay.get(key) or {}
            subj = ReviewSubject(subject_type=SUBJECT_TYPE, subject_ref=key,
                                 current_state=derived)
            s.add(subj)
            s.flush()  # need subj.id for the task
            s.add(LifecycleTransition(
                subject_type=SUBJECT_TYPE, subject_ref=key,
                from_status=None, to_status=derived,
                actor="migration", actor_role=None, reason="element-state migration",
                occurred_at=_parse_ts(ov.get("submitted_at")) or func.now(),
            ))
            # Review task: open for in_review; closed (with the overlay decision) otherwise.
            if derived == "in_review":
                s.add(ReviewTask(review_subject_id=subj.id, task_type=TASK_TYPE, state="open"))
            elif derived in ("approved", "rejected", "returned"):
                task_state = "approved" if derived == "approved" else "rejected"
                s.add(ReviewTask(
                    review_subject_id=subj.id, task_type=TASK_TYPE, state=task_state,
                    decided_by=ov.get("decided_by"), decided_by_role=ov.get("decided_by_role"),
                    decision=derived, reason=ov.get("reject_reason"),
                    decided_at=_parse_ts(ov.get("decided_at")),
                ))

            stats["written"] += 1
            stats["by_status"][derived] = stats["by_status"].get(derived, 0) + 1

    return stats


def _main() -> None:
    ap = argparse.ArgumentParser(description="Migrate element-state lifecycle slice → Postgres")
    ap.add_argument("--yaml", default=str(_DEFAULT_YAML))
    ap.add_argument("--force", action="store_true", help="truncate element rows before load")
    args = ap.parse_args()
    stats = migrate_element_states(yaml_path=args.yaml, force=args.force)
    print("Element-lifecycle migration:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _main()
