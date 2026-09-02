"""Shared read connection for the BIRD Knowledge Base — Postgres schema `bird` (Phase 1.3).

The KB moved from a standalone DuckDB file to the `bird` schema in the main Postgres database
(see migration `0019_bird_knowledge_base` + `knowledge_base/bird/loader/bird_kb_postgres_loader.py`).
`BirdConn` keeps the DuckDB-style positional `?` placeholders so the call sites written against
the old DuckDB connection (`api/routes/bird.py`, `agents/chat_agent.py`) need no rewrite beyond
the schema's own column-name differences (see BIRD_KB_TRAPS below).

BIRD_KB_FRAMEWORKS scopes every query in this module's callers to the BIRD Knowledge Base only.
The same `bird` schema also holds eight non-BIRD frameworks (EBA_FINREP, FINREP_REF, EBA_AE, SDD,
AE_REF, ANCRDT's sibling rows, ECB2_SHS, SHS_REF) loaded as the future Regulatory KB's seed data
(see mapping-redesign-decisions.md Decision Point 21) — not exposed anywhere yet.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import text as _sql_text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from core.glossary_db.db import session_scope

# The BIRD Knowledge Base proper: BIRD itself plus AnaCredit (its ROL/output layer uses
# framework_id='ANCRDT' instead of a cube_type). Everything else in the `bird` schema belongs
# to the future Regulatory KB and must never leak through these endpoints.
BIRD_KB_FRAMEWORKS = ("BIRD", "ANCRDT")


def _to_named(sql: str, params: list) -> tuple[str, dict[str, Any]]:
    """Convert DuckDB-style positional '?' placeholders into SQLAlchemy named binds."""
    named: dict[str, Any] = {}
    counter = 0

    def _repl(_match: "re.Match[str]") -> str:
        nonlocal counter
        key = f"p{counter}"
        named[key] = params[counter]
        counter += 1
        return f":{key}"

    return re.sub(r"\?", _repl, sql), named


class BirdConn:
    """Adapts a SQLAlchemy session to the '?'-placeholder execute().fetchall() shape."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def execute(self, sql: str, params: list | None = None) -> CursorResult:
        named_sql, named_params = _to_named(sql, params or [])
        return self._session.execute(_sql_text(named_sql), named_params)


@contextmanager
def bird_conn() -> Iterator[BirdConn]:
    """Connection to the `bird` schema, scoped like every other Postgres-backed store.

    Sets search_path to `bird` (falling back to `public`) so every query below can keep using
    bare table names (`cube`, `domain`, ...) exactly as they were written against the DuckDB KB.
    """
    with session_scope() as session:
        session.execute(_sql_text("SET search_path TO bird, public"))
        yield BirdConn(session)
