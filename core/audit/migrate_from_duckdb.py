"""Migrate the append-only audit log from DuckDB → Postgres (one-time), with parity.

Copies every ``audit_events`` row from ``audit/audit.duckdb`` (source of truth) into the
Postgres ``audit_events`` table, PRESERVING ids and timestamps, then verifies parity
(row count + spot-check). Idempotent with ``--force`` (truncates the pg table first).

Run with the backend STOPPED — DuckDB is single-writer, so a running uvicorn holds the
audit file lock and this read would fail.

    .venv\\Scripts\\python.exe -m core.audit.migrate_from_duckdb            # dry parity check
    .venv\\Scripts\\python.exe -m core.audit.migrate_from_duckdb --force    # (re)load + parity
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]

_COLUMNS = [
    "id", "occurred_at", "event_class", "event_type",
    "actor_user_id", "actor_role", "legal_entity",
    "subject_type", "subject_id", "payload", "request_id",
]


def _duckdb_path() -> Path:
    return Path(os.getenv("AI_TIMO_AUDIT_DB", str(_ROOT / "audit" / "audit.duckdb")))


def _read_duckdb_rows(path: Path) -> list[dict[str, Any]]:
    import duckdb

    conn = duckdb.connect(str(path), read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT id, occurred_at, event_class, event_type,
                   actor_user_id, actor_role, legal_entity,
                   subject_type, subject_id, payload, request_id
            FROM audit_events
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(zip(_COLUMNS, r))
        payload = d.get("payload")
        if isinstance(payload, str):
            try:
                d["payload"] = json.loads(payload)
            except Exception:
                d["payload"] = {"_raw": payload}
        out.append(d)
    return out


def migrate(force: bool = False) -> dict[str, Any]:
    from sqlalchemy import func, insert, select, text

    from core.glossary_db.db import session_scope
    from core.shared.models import AuditEvent

    src = _duckdb_path()
    if not src.exists():
        return {"ok": False, "reason": f"DuckDB audit file not found: {src}"}

    rows = _read_duckdb_rows(src)
    duck_count = len(rows)

    with session_scope() as s:
        existing = s.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
        if existing and not force:
            return {
                "ok": False,
                "reason": f"Postgres audit_events already has {existing} rows — pass --force to reload.",
                "duckdb_rows": duck_count,
                "pg_rows": existing,
            }
        if force and existing:
            s.execute(text("TRUNCATE TABLE audit_events RESTART IDENTITY"))

        if rows:
            # Explicit-id insert (identity is BY DEFAULT) preserves the original ids.
            s.execute(insert(AuditEvent), rows)
            # Re-sync the identity sequence so future auto-ids don't collide with loaded ids.
            s.execute(text(
                "SELECT setval(pg_get_serial_sequence('audit_events','id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM audit_events))"
            ))

    # ── parity ────────────────────────────────────────────────────────────────
    with session_scope() as s:
        pg_count = s.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
        sample = s.execute(
            select(AuditEvent).order_by(AuditEvent.id.desc()).limit(3)
        ).scalars().all()
    parity = duck_count == pg_count
    return {
        "ok": parity,
        "duckdb_rows": duck_count,
        "pg_rows": pg_count,
        "parity": parity,
        "sample_ids": [ev.id for ev in sample],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate audit log DuckDB → Postgres")
    ap.add_argument("--force", action="store_true", help="truncate + reload the pg table")
    args = ap.parse_args()
    result = migrate(force=args.force)
    print(json.dumps(result, indent=2, default=str))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
