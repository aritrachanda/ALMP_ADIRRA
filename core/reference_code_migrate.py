"""Phase 5b.2 — migrate the inline Reference Data slice of ``element_states.yaml`` into Postgres.

Reads the ``metadata`` map (``refdata_meanings`` / ``refdata_values`` / ``refdata_status`` /
``refdata_bound_set_id``) and materialises one ``reference_code`` row per documented code for
every **unbound** coded field, using a value-preserving status map so DQ scores do not move:

    field refdata_status        per-code status     derive_set_status → (DQ status)
    ─────────────────────       ───────────────     ───────────────────────────────
    approved                    approved            approved
    under_review                in_review           under_review
    candidate                   draft               candidate
    (absent / none)             draft               candidate   ← flagged by parity (regression)

**Bound** fields (``refdata_bound_set_id`` set) are deliberately skipped — their codes stay
set-driven (the binding lives in element_state metadata, unchanged); the DQ provider reads the
reference set directly for those. Per-code editing applies to unbound/local fields only (D5).

Idempotent: ``force=True`` truncates the reference_code rows + their transitions first.

CLI:  python -m core.reference_code_migrate [--force] [--yaml PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select

from core.glossary_db.db import session_scope
from core.shared.models import LifecycleTransition, ReferenceCode
from core.reference_code_repo import SUBJECT_TYPE, derive_set_status

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_YAML = _ROOT / "governance" / "element_states.yaml"

#: field refdata_status → per-code status (value-preserving; see module docstring).
STATUS_MAP = {
    "approved": "approved",
    "under_review": "in_review",
    "candidate": "draft",
    "none": "draft",
    None: "draft",
}


def _load(yaml_path: Path) -> dict:
    if not yaml_path.exists():
        return {}
    with yaml_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _unbound_refdata_fields(data: dict) -> dict[str, dict[str, Any]]:
    """Return ``{element_key: metadata}`` for coded fields with inline meanings and no binding."""
    md = data.get("metadata", {}) or {}
    out: dict[str, dict[str, Any]] = {}
    for key, meta in md.items():
        meta = meta or {}
        if meta.get("refdata_bound_set_id"):
            continue  # bound → set-driven, skip
        if meta.get("refdata_meanings") or meta.get("refdata_values"):
            out[key] = meta
    return out


def _rows_for_field(meta: dict[str, Any]) -> list[dict[str, Any]]:
    meanings = meta.get("refdata_meanings") or {}
    values = meta.get("refdata_values") or {}
    per_code_status = STATUS_MAP.get(meta.get("refdata_status"), "draft")
    rows: list[dict[str, Any]] = []
    for code in sorted(set(meanings) | set(values)):
        meaning = meanings.get(code)
        value = values.get(code)
        has_content = bool(str(meaning or "").strip() or str(value or "").strip())
        rows.append({
            "code": str(code),
            "value": value or None,
            "meaning": meaning or None,
            "origin": "profiled",
            "status": per_code_status if has_content else "empty",
        })
    return rows


def parity_rows(*, yaml_path: Path | str = _DEFAULT_YAML) -> list[dict[str, Any]]:
    """Per-field old field-status vs new derived set-status (the parity evidence)."""
    data = _load(Path(yaml_path))
    rows: list[dict[str, Any]] = []
    for key, meta in sorted(_unbound_refdata_fields(data).items()):
        new_rows = _rows_for_field(meta)
        old_status = str(meta.get("refdata_status") or "none").lower()
        new_status = derive_set_status(new_rows)
        rows.append({
            "key": key,
            "old_status": old_status,
            "new_status": new_status,
            "match": old_status == new_status,
            "codes": len(new_rows),
        })
    return rows


def migrate_reference_codes(*, yaml_path: Path | str = _DEFAULT_YAML,
                            dsn: str | None = None, force: bool = False) -> dict[str, Any]:
    """Load the per-code reference rows into Postgres. Returns a stats dict."""
    data = _load(Path(yaml_path))
    fields = _unbound_refdata_fields(data)

    stats: dict[str, Any] = {
        "fields": len(fields), "codes_written": 0, "by_status": {},
        "parity_mismatches": [],
    }

    with session_scope(dsn) as s:
        if force:
            keys = list(fields)
            if keys:
                s.execute(delete(ReferenceCode).where(ReferenceCode.element_key.in_(keys)))
                refs = [f"{k}|{c['code']}" for k in keys for c in _rows_for_field(fields[k])]
                if refs:
                    s.execute(delete(LifecycleTransition).where(
                        LifecycleTransition.subject_type == SUBJECT_TYPE,
                        LifecycleTransition.subject_ref.in_(refs)))

        for key, meta in sorted(fields.items()):
            new_rows = _rows_for_field(meta)
            # Skip if a prior (non-force) run already loaded this field.
            existing = s.execute(
                select(ReferenceCode.code).where(ReferenceCode.element_key == key)
            ).scalars().all()
            existing_set = set(existing)
            for row in new_rows:
                if row["code"] in existing_set:
                    continue
                submitted = row["status"] == "in_review"
                approved = row["status"] == "approved"
                s.add(ReferenceCode(
                    element_key=key, code=row["code"], value=row["value"],
                    meaning=row["meaning"], origin=row["origin"], status=row["status"],
                    submitted_by="migration" if submitted else None,
                    approved_by="migration" if approved else None,
                ))
                s.add(LifecycleTransition(
                    subject_type=SUBJECT_TYPE, subject_ref=f"{key}|{row['code']}",
                    from_status=None, to_status=row["status"],
                    actor="migration", actor_role=None, reason="reference-data migration",
                ))
                stats["codes_written"] += 1
                stats["by_status"][row["status"]] = stats["by_status"].get(row["status"], 0) + 1

            old_status = str(meta.get("refdata_status") or "none").lower()
            new_status = derive_set_status(new_rows)
            if old_status != new_status:
                stats["parity_mismatches"].append(
                    {"key": key, "old": old_status, "new": new_status})

    return stats


def _main() -> None:
    ap = argparse.ArgumentParser(description="Migrate Reference Data (per-code) → Postgres")
    ap.add_argument("--yaml", default=str(_DEFAULT_YAML))
    ap.add_argument("--force", action="store_true", help="truncate reference_code rows before load")
    args = ap.parse_args()
    stats = migrate_reference_codes(yaml_path=args.yaml, force=args.force)
    print("Reference-data (per-code) migration:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("\nParity (old field status vs new derived set status):")
    for row in parity_rows(yaml_path=args.yaml):
        flag = "OK " if row["match"] else "!! "
        print(f"  {flag}{row['key']}: {row['old_status']} -> {row['new_status']} ({row['codes']} codes)")


if __name__ == "__main__":
    _main()
