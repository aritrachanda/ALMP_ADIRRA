"""Shared Postgres-unreachable guard (govern-pg-s0-foundations, postgres-backend-resilience).

One reusable check for "is this feature's Postgres backend actually up right now", used by
every Postgres-backed feature — not just one. Deliberately FastAPI-free (``core/`` never
imports FastAPI anywhere in this codebase) so it stays usable from any layer; the HTTP shaping
(the clean 503) lives in ``api/main.py``'s registered exception handler for
:class:`DatabaseUnavailableError`.

Usage — call once, at the point a feature is about to actually touch Postgres::

    from core.shared.db_availability import require_reachable
    from core.catalog_db import backend as catalog_backend

    require_reachable(catalog_backend, "Catalog")
"""
from __future__ import annotations

from typing import Callable


class DatabaseUnavailableError(Exception):
    """Raised when a feature's backend flag says 'postgres' but the database is unreachable."""

    def __init__(self, service_label: str) -> None:
        self.service_label = service_label
        super().__init__(f"{service_label} database is not running.")


def require_reachable(backend_getter: Callable[[], str], service_label: str) -> None:
    """Raise :class:`DatabaseUnavailableError` if *backend_getter* says 'postgres' but the
    shared Postgres connection is unreachable. A no-op (near-free) when the backend is 'yaml'.
    """
    if backend_getter() != "postgres":
        return
    from core.glossary_db.db import health

    if not health():
        raise DatabaseUnavailableError(service_label)
