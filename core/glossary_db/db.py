"""Engine, session and connection helpers for the Business Glossary v2 Postgres store.

Streamlit-free and app-agnostic. The DSN comes from project.yaml (``database:``) + the
password env var, per the repo convention — with an ``ADM_DATABASE_URL`` override so tests
can point at a throwaway database. Synchronous psycopg 3 driver (route handlers run in
FastAPI's threadpool; never call these inside an ``async def``).
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_ROOT = Path(__file__).resolve().parents[2]

# One engine per DSN (tests use a different DSN than the app).
_ENGINES: dict[str, Engine] = {}
_SESSIONMAKERS: dict[str, sessionmaker] = {}


def _project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


#: Cache of the assembled DSN (everything except the live ADM_DATABASE_URL override below).
#: Found live 2026-08-14: build_dsn() re-read + re-parsed project.yaml AND reloaded .env on
#: EVERY call (~5ms each, measured) -- with no caller ever passing an explicit dsn, every
#: Postgres-backed store's every single query paid this tax. A source with ~1,900 columns
#: (ALM Bank) made ~1,900+ of these calls just building its Source Profile aggregation,
#: dwarfing the actual database round-trip time. Same config-cached-at-import convention
#: already used elsewhere in this codebase (e.g. semantic_backend()) -- a real config change
#: needs an app restart regardless, so this adds no new caveat.
_DSN_CACHE: str | None = None


def build_dsn() -> str:
    """Assemble the Postgres DSN. ``ADM_DATABASE_URL`` (if set) wins — used by tests.

    Everything else is computed once and cached — project.yaml/`.env` don't change without
    an app restart, so re-reading them on every call was pure waste (see _DSN_CACHE above).
    """
    override = os.environ.get("ADM_DATABASE_URL")
    if override:
        return override
    global _DSN_CACHE
    if _DSN_CACHE is not None:
        return _DSN_CACHE
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except Exception:
        pass
    db = _project().get("database", {}) or {}
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    name = db.get("name", "adm")
    user = db.get("user", "adm")
    password = os.environ.get(db.get("password_env", "ADM_DB_PASSWORD"), "adm_local_dev")
    _DSN_CACHE = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
    return _DSN_CACHE


def backend() -> str:
    """Return the configured glossary backend: 'yaml' (default) or 'postgres'."""
    env = os.environ.get("ADIRRA_GLOSSARY_BACKEND")
    if env:
        return env.strip().lower()
    db = _project().get("database", {}) or {}
    return str(db.get("glossary_backend", "yaml")).strip().lower()


def _json_default(obj):
    """Fallback for JSONB values that aren't natively JSON-serializable. date/datetime use
    standard ISO 8601 (with the 'T' separator) rather than Python's str() (space-separated) —
    everything else (Decimal, etc.) falls back to str().

    TODO(2026-08-05): duplicates core.shared.json_utils.json_default (extracted for Catalog).
    Point this at the shared one too once Glossary's own Postgres cutover is revisited.
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def get_engine(dsn: str | None = None) -> Engine:
    url = dsn or build_dsn()
    if url not in _ENGINES:
        # connect_timeout bounds a dead-database connect to a few seconds so the app fails
        # fast (503) and health()/tests never hang on an unreachable host/port.
        # json_serializer's default fallback covers JSONB values that aren't natively
        # JSON-serializable (date/datetime/Decimal, etc.) rather than raising mid-write.
        _ENGINES[url] = create_engine(
            url, pool_pre_ping=True, future=True,
            connect_args={"connect_timeout": 3},
            json_serializer=lambda obj: json.dumps(obj, default=_json_default),
        )
        _SESSIONMAKERS[url] = sessionmaker(bind=_ENGINES[url], future=True, expire_on_commit=False)
    return _ENGINES[url]


def get_sessionmaker(dsn: str | None = None) -> sessionmaker:
    get_engine(dsn)
    return _SESSIONMAKERS[dsn or build_dsn()]


@contextmanager
def session_scope(dsn: str | None = None) -> Iterator[Session]:
    """Transactional session scope: commit on success, rollback on error, always close."""
    session = get_sessionmaker(dsn)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health(dsn: str | None = None) -> bool:
    """Return True if the database answers a trivial query, else False (never raises)."""
    try:
        eng = get_engine(dsn)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def dispose_all() -> None:
    """Dispose every cached engine (used by tests between DSNs)."""
    for eng in _ENGINES.values():
        eng.dispose()
    _ENGINES.clear()
    _SESSIONMAKERS.clear()
