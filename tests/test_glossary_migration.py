"""Phase 3 tests: the glossary YAML->Postgres migration, parity, and idempotency.

Runs against a throwaway ``adm_test`` database (migrating the real glossary.yaml into it).
Skipped when Postgres is unreachable.
"""
from __future__ import annotations

import os

import pytest

from core.glossary_db import db as gdb

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        from sqlalchemy import text
        with gdb.get_engine(_BASE_DSN).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run migration tests",
                allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone():
            conn.execute("CREATE DATABASE adm_test")

    prev_url = os.environ.get("ADM_DATABASE_URL")
    prev_backend = os.environ.get("ADIRRA_GLOSSARY_BACKEND")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    os.environ["ADIRRA_GLOSSARY_BACKEND"] = "postgres"
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")

    yield

    gdb.dispose_all()
    for k, v in (("ADM_DATABASE_URL", prev_url), ("ADIRRA_GLOSSARY_BACKEND", prev_backend)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _migrate():
    from core.glossary_db.migrate_from_yaml import run_migration
    with gdb.session_scope(_TEST_DSN) as s:
        return run_migration(s, force=True)


def test_migration_counts_and_1a_validation():
    rep = _migrate()
    assert rep.terms_in == rep.terms_out == 180
    assert rep.synonyms_in == rep.synonyms_out
    assert rep.tags_in == rep.tags_out
    # the migration parser must agree with the Phase-1a profile exactly
    assert rep.validation_mismatches == []
    # status canonicalisation must not silently re-grade the catalog
    assert rep.status_changed == []
    assert rep.dq_changed == []
    # expected triage volume (unresolvable catalog refs)
    assert sum(rep.triage_by_reason.values()) == 62


def test_parity_yaml_vs_postgres():
    _migrate()
    from core.glossary_db.migrate_from_yaml import parity_check
    with gdb.session_scope(_TEST_DSN) as s:
        divergences = parity_check(s)
    assert divergences == [], divergences


def test_migration_is_idempotent():
    r1 = _migrate()
    r2 = _migrate()  # re-run over populated store (force) → identical end state
    assert r1.terms_out == r2.terms_out == 180
    assert dict(r1.triage_by_reason) == dict(r2.triage_by_reason)
    from core.glossary_db.models import Term, Linkage, LinkageTriage
    from sqlalchemy import func, select
    with gdb.session_scope(_TEST_DSN) as s:
        assert s.execute(select(func.count()).select_from(Term)).scalar_one() == 180
        # no duplicate accumulation across re-runs
        assert s.execute(select(func.count()).select_from(LinkageTriage)).scalar_one() == 62
        assert s.execute(select(func.count()).select_from(Linkage)).scalar_one() > 0


def test_refuses_nonempty_without_force():
    _migrate()  # populate
    from core.glossary_db.migrate_from_yaml import run_migration
    with pytest.raises(SystemExit):
        with gdb.session_scope(_TEST_DSN) as s:
            run_migration(s, force=False)
