"""Append-only DuckDB-backed audit event store.

Usage (API startup)
-------------------
    store = AuditStore(db_path)
    set_current_store(store)          # makes it accessible app-wide
    app.state.audit_store = store

Usage (anywhere in the app)
----------------------------
    from core.audit import get_current_store
    store = get_current_store()
    if store:
        store.log_business(events.MAPPING_CANDIDATE_ACCEPTED, ...)

AI calls
--------
    from core.audit.store import record_ai_call
    record_ai_call(response, model=model, subject_type="mapping", subject_id="banking_to_bird",
                   prompt_tokens=100, completion_tokens=50, latency_ms=1200)
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import duckdb

_log = logging.getLogger(__name__)


def _pid_alive(pid: int) -> bool:
    """Return True if a process with this PID is currently running."""
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

# Module-level singleton — set by the FastAPI lifespan, readable by agents.
_current_store: "AuditStore | None" = None
_lock = threading.Lock()


def set_current_store(store: "AuditStore") -> None:
    global _current_store
    with _lock:
        _current_store = store


def get_current_store() -> "AuditStore | None":
    return _current_store


_DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id            BIGINT PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL,
    event_class   VARCHAR     NOT NULL,
    event_type    VARCHAR     NOT NULL,
    actor_user_id VARCHAR,
    actor_role    VARCHAR,
    legal_entity  VARCHAR,
    subject_type  VARCHAR,
    subject_id    VARCHAR,
    payload       JSON,
    request_id    VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_subject     ON audit_events (subject_type, subject_id);
"""


class AuditStore:
    """Thread-safe append-only audit log backed by DuckDB."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open_db()
        self._conn.execute(_DDL)
        self._seq = self._next_id()
        self._write_lock = threading.Lock()
        # Release the DuckDB lock on any normal interpreter exit — covers the
        # graceful paths a hard kill (taskkill /F) skips, so a cleanly-stopped
        # process never leaves the audit DB locked for the next start.
        atexit.register(self.close)

    def _open_db(self) -> duckdb.DuckDBPyConnection:
        """Open the DuckDB file, removing stale locks from dead processes."""
        for attempt in range(3):
            try:
                return duckdb.connect(str(self._db_path))
            except duckdb.IOException as exc:
                msg = str(exc)
                m = re.search(r"PID\s+(\d+)", msg)
                stale_pid = int(m.group(1)) if m else None

                # Determine if we can safely remove the locked file(s).
                # Case 1: error embeds a PID we can verify is dead.
                # Case 2: WAL file locked with no PID — treat as stale on retries.
                is_wal_error = ".wal" in msg and "being used by another process" in msg
                can_remove = (stale_pid and not _pid_alive(stale_pid)) or (is_wal_error and attempt > 0)

                if can_remove:
                    _log.warning(
                        "Removing stale DuckDB lock (PID=%s, wal_error=%s): %s",
                        stale_pid, is_wal_error, self._db_path,
                    )
                    wal = self._db_path.with_suffix(".duckdb.wal")
                    wal.unlink(missing_ok=True)
                    bak = self._db_path.with_suffix(".duckdb.bak")
                    try:
                        self._db_path.rename(bak)
                    except OSError:
                        self._db_path.unlink(missing_ok=True)
                    continue
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                # Final attempt failed and the holder is still alive: this is
                # almost always a stray backend / uvicorn --reload worker left
                # running from a previous session. Give an actionable message
                # (exact PID + tree-kill command) instead of a cryptic DuckDB
                # IOException the user can't act on.
                if stale_pid and _pid_alive(stale_pid):
                    raise RuntimeError(
                        f"Audit DB '{self._db_path}' is locked by a still-running process "
                        f"(PID {stale_pid}) — likely a stray backend / uvicorn --reload worker "
                        f"from a previous run. Stop it and its children, then restart:\n"
                        f"    taskkill /PID {stale_pid} /T /F      (Windows)\n"
                        f"    kill {stale_pid}                     (macOS / Linux)"
                    ) from exc
                raise

    # ── internal ─────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_events").fetchone()
        return (row[0] if row else 0) + 1

    def _append(self, event_class: str, event_type: str, subject_type: str | None,
                subject_id: str | None, payload: dict[str, Any], *,
                actor_user_id: str | None = None, actor_role: str | None = None,
                legal_entity: str | None = None, request_id: str | None = None) -> int:
        with self._write_lock:
            row_id = self._seq
            self._seq += 1
            self._conn.execute(
                """
                INSERT INTO audit_events
                    (id, occurred_at, event_class, event_type,
                     actor_user_id, actor_role, legal_entity,
                     subject_type, subject_id, payload, request_id)
                VALUES (?, now(), ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row_id, event_class, event_type,
                    actor_user_id, actor_role, legal_entity,
                    subject_type, subject_id,
                    json.dumps(payload, default=str),
                    request_id,
                ],
            )
        return row_id

    # ── public write API ─────────────────────────────────────────────────────

    def log_business(
        self,
        event_type: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
        actor_role: str | None = None,
        legal_entity: str | None = None,
        request_id: str | None = None,
    ) -> int:
        return self._append(
            "business", event_type, subject_type, subject_id, payload,
            actor_user_id=actor_user_id, actor_role=actor_role,
            legal_entity=legal_entity, request_id=request_id,
        )

    def log_ai_call(
        self,
        *,
        model: str,
        subject_type: str,
        subject_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        confidence: float | None = None,
        prompt_id: str | None = None,
        retrieval_chunks: int | None = None,
        extra: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> int:
        payload: dict[str, Any] = {
            "model": model,
            "prompt_id": prompt_id,
            "retrieval_chunks": retrieval_chunks,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": round(latency_ms, 1),
            "confidence": confidence,
        }
        if extra:
            payload.update(extra)
        return self._append(
            "ai", "ai.call", subject_type, subject_id, payload,
            request_id=request_id,
        )

    # ── read API ──────────────────────────────────────────────────────────────

    def list_events(
        self,
        *,
        event_class: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        filters: list[str] = []
        params: list[Any] = []

        if event_class:
            filters.append("event_class = ?")
            params.append(event_class)
        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if event_prefix:
            filters.append("event_type LIKE ?")
            params.append(f"{event_prefix}%")
        if subject_type:
            filters.append("subject_type = ?")
            params.append(subject_type)
        if subject_id:
            filters.append("subject_id LIKE ?")
            params.append(f"%{subject_id}%")
        if from_ts:
            filters.append("occurred_at >= ?::TIMESTAMPTZ")
            params.append(from_ts)
        if to_ts:
            filters.append("occurred_at <= ?::TIMESTAMPTZ")
            params.append(to_ts)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params += [limit, offset]

        rows = self._conn.execute(
            f"""
            SELECT id, occurred_at::TEXT, event_class, event_type,
                   actor_user_id, actor_role, legal_entity,
                   subject_type, subject_id, payload, request_id
            FROM audit_events
            {where}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

        return [_row_to_dict(r) for r in rows]

    def get_event(self, event_id: int) -> dict | None:
        row = self._conn.execute(
            """
            SELECT id, occurred_at::TEXT, event_class, event_type,
                   actor_user_id, actor_role, legal_entity,
                   subject_type, subject_id, payload, request_id
            FROM audit_events WHERE id = ?
            """,
            [event_id],
        ).fetchone()
        return _row_to_dict(row) if row else None

    def summary(self, days: int = 30) -> list[dict]:
        """Counts per (day, event_type) for the last N days."""
        rows = self._conn.execute(
            """
            SELECT strftime(occurred_at, '%Y-%m-%d') AS day,
                   event_type,
                   COUNT(*) AS cnt
            FROM audit_events
            WHERE occurred_at >= (now() - INTERVAL (? || ' days'))::TIMESTAMPTZ
            GROUP BY 1, 2
            ORDER BY 1 DESC, 3 DESC
            """,
            [str(days)],
        ).fetchall()
        return [{"day": r[0], "event_type": r[1], "count": r[2]} for r in rows]

    def close(self) -> None:
        # Idempotent: the lifespan shutdown and the atexit hook may both fire.
        conn = self._conn
        if conn is None:
            return
        self._conn = None
        try:
            conn.close()
        except Exception:
            pass


def _row_to_dict(row: tuple) -> dict:
    keys = ["id", "occurred_at", "event_class", "event_type",
            "actor_user_id", "actor_role", "legal_entity",
            "subject_type", "subject_id", "payload", "request_id"]
    d = dict(zip(keys, row))
    if isinstance(d.get("payload"), str):
        try:
            d["payload"] = json.loads(d["payload"])
        except (ValueError, TypeError):
            pass
    return d


# ── Convenience helper for agents ───────────────────────────────────────────

def record_ai_call(
    *,
    model: str,
    subject_type: str,
    subject_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: float = 0.0,
    confidence: float | None = None,
    prompt_id: str | None = None,
    retrieval_chunks: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an AI call if a store is registered. No-op otherwise."""
    store = get_current_store()
    if store is None:
        return
    store.log_ai_call(
        model=model, subject_type=subject_type, subject_id=subject_id,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        latency_ms=latency_ms, confidence=confidence,
        prompt_id=prompt_id, retrieval_chunks=retrieval_chunks, extra=extra,
    )
