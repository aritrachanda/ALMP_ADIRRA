"""Shared, safe test-isolation helper (Slice F, interim/narrow -- see tech-debt.md's
"permanently hard-gate the test suite" entry for the real, deferred fix).

Some tests must exercise the REAL Postgres catalog (so they cannot redirect to a throwaway
test database) but write ``semantic_type_assignment`` rows keyed by REAL catalog columns
(e.g. ``banking|src|accounts|iban``). A plain wipe-before/after would either permanently
destroy a real, pre-existing governance decision for that column, or -- if that row already
has real submission history -- cascade-delete that real history when the row is removed.

This instead snapshots every row already present under a given key prefix (typically a whole
source, e.g. ``"banking|"``) before each test, then restores each row's exact original column
values afterward via an in-place UPDATE (never touches the row's real ``id``, so any real
linked history stays correctly attached). A row the test created from nothing (never existed
before) is deleted afterward -- always safe, since nothing real could reference an id that
never existed until that test run.
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest
from sqlalchemy import select

from core.glossary_db import db as gdb
from core.glossary_db.db import session_scope
from core.shared.models import ElementDefinition, SemanticTypeAssignment

_RESTORE_COLUMNS = tuple(c.name for c in SemanticTypeAssignment.__table__.columns if c.name != "id")
_DEFINITION_RESTORE_COLUMNS = tuple(c.name for c in ElementDefinition.__table__.columns if c.name != "id")


def _restore_rows(model, key_column, prefix: str, restore_columns: tuple[str, ...]):
    """Shared snapshot/restore implementation for a table keyed by a text column, scoped to a
    prefix. See module docstring for why this is a restore, never a delete, for real rows."""

    @pytest.fixture(autouse=True)
    def _restore() -> Iterator[None]:
        try:
            with session_scope() as s:
                rows = s.execute(select(model).where(key_column.like(f"{prefix}%"))).scalars().all()
                before = {getattr(row, key_column.key): {c: getattr(row, c) for c in restore_columns} for row in rows}
        except Exception:
            before = None  # Postgres unreachable -- the test below fails on its own merits

        yield

        if before is None:
            return
        try:
            with session_scope() as s:
                rows = s.execute(select(model).where(key_column.like(f"{prefix}%"))).scalars().all()
                for row in rows:
                    key_value = getattr(row, key_column.key)
                    original = before.get(key_value)
                    if original is None:
                        s.delete(row)
                    else:
                        for col, value in original.items():
                            setattr(row, col, value)
        except Exception:
            pass

    return _restore


def restore_real_element_definitions(prefix: str):
    """Fixture factory mirroring ``restore_real_semantic_type_rows``, but for
    ``element_definition`` rows (description/business name) -- needed by tests that must
    temporarily blank a real, already-governed column's real content to exercise a gate check,
    then have it restored exactly afterward.
    """
    return _restore_rows(ElementDefinition, ElementDefinition.element_key, prefix, _DEFINITION_RESTORE_COLUMNS)


def sandbox_semantic_type_tests():
    """Fixture factory for test modules that construct ``SemanticResolver``/``SemanticTypeStore``
    directly against synthetic, hand-built profile dicts and never touch the real catalog --
    safe to fully redirect to the throwaway ``adm_test`` database for the whole module. Mirrors
    the proven ``_adm_test_db()`` pattern already used by ``tests/test_semantic_type_repo.py``
    and others; skips the whole module if Postgres isn't reachable at all.

    Returns ``(module_db_fixture, per_test_wipe_fixture)`` -- assign BOTH at module scope, e.g.
    ``_sandbox_db, _sandbox_wipe = sandbox_semantic_type_tests()``. The wipe fixture is needed
    because many test modules reuse the exact same literal keys (e.g. ``banking|src|accounts|
    iban``) and the sticky confirmed/rejected disposition rule would otherwise let one test's
    state silently leak into the next.
    """
    base_dsn = gdb.build_dsn()
    test_dsn = base_dsn.rsplit("/", 1)[0] + "/adm_test"

    def _pg_available() -> bool:
        try:
            import psycopg  # noqa: F401
            from sqlalchemy import text
            eng = gdb.get_engine(base_dsn)
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    if not _pg_available():
        pytest.skip("PostgreSQL not reachable", allow_module_level=True)

    @pytest.fixture(scope="module", autouse=True)
    def _adm_test_db() -> Iterator[None]:
        import psycopg
        raw = base_dsn.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(raw, autocommit=True) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone()
            if not exists:
                conn.execute("CREATE DATABASE adm_test")

        prev_url = os.environ.get("ADM_DATABASE_URL")
        os.environ["ADM_DATABASE_URL"] = test_dsn
        gdb.dispose_all()

        from alembic import command
        from alembic.config import Config
        cfg = Config("db/alembic.ini")
        command.upgrade(cfg, "head")

        yield

        gdb.dispose_all()
        if prev_url is None:
            os.environ.pop("ADM_DATABASE_URL", None)
        else:
            os.environ["ADM_DATABASE_URL"] = prev_url

    @pytest.fixture(autouse=True)
    def _wipe_between_tests() -> Iterator[None]:
        from sqlalchemy import delete

        def _wipe():
            # Defensive: only ever wipe the throwaway test database, never anything else.
            if "/adm_test" not in os.environ.get("ADM_DATABASE_URL", ""):
                return
            with session_scope() as s:
                s.execute(delete(SemanticTypeAssignment))

        _wipe()
        yield
        _wipe()

    return _adm_test_db, _wipe_between_tests

    return _adm_test_db


def restore_real_semantic_type_rows(prefix: str):
    """Fixture factory: returns an autouse fixture restoring every ``semantic_type_assignment``
    row whose key starts with *prefix* to its exact pre-test state (or removing it if the test
    created it from nothing). Assign the result to a module-level name so pytest picks it up,
    e.g. ``_restore_banking = restore_real_semantic_type_rows("banking|")``.
    """
    return _restore_rows(SemanticTypeAssignment, SemanticTypeAssignment.key, prefix, _RESTORE_COLUMNS)

