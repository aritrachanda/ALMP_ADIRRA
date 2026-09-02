"""S0 foundations — data-dictionary comment coverage (govern-pg-s0-foundations, task 2.5).

Verifies migration 0009_add_data_dictionary_comments actually landed: every one of the 18
tables that existed before S0 has a table comment, and a representative column per table has
a column comment too (not all 281 — this is a regression guard, not a full re-assertion of the
migration's own content). Runs against a throwaway ``adm_test`` database, same pattern as
tests/test_catalog_db_repository.py.
"""
from __future__ import annotations

import os

import pytest

from core.glossary_db import db as gdb

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        import psycopg  # noqa: F401
        from sqlalchemy import text
        with gdb.get_engine(_BASE_DSN).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run this test",
                allow_module_level=True)


# One representative column per pre-S0 table (the one most likely to matter if a future
# migration accidentally drops/omits a comment on it).
_SAMPLE_COLUMN_PER_TABLE = {
    "glossary": "name",
    "term": "status",
    "term_version": "business_description",
    "term_relation": "relation_type",
    "linkage": "raw_ref",
    "lifecycle_transition": "to_status",
    "review_subject": "current_state",
    "linkage_triage": "reason",
    "glossary_group_meta": "description",
    "review_task": "state",
    "reference_code": "meaning",
    "audit_events": "event_type",
    "catalog_source": "source_name",
    "catalog_dataset": "table_name",
    "catalog_element": "column_name",
    "catalog_refresh_event": "changed",
    "catalog_dataset_snapshot": "fingerprint",
    "catalog_element_snapshot": "fingerprint",
}


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    """Create adm_test (if needed), migrate it to head, and point the app at it."""
    import psycopg

    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone()
        if not exists:
            conn.execute("CREATE DATABASE adm_test")

    prev_url = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")

    yield

    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


def test_every_pre_s0_table_has_a_table_comment():
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    with eng.connect() as c:
        for table in _SAMPLE_COLUMN_PER_TABLE:
            comment = c.execute(text(f"SELECT obj_description('{table}'::regclass)")).scalar()
            assert comment, f"{table} has no table comment"


def test_representative_column_per_table_has_a_comment():
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    with eng.connect() as c:
        for table, column in _SAMPLE_COLUMN_PER_TABLE.items():
            comment = c.execute(text(
                "SELECT col_description(a.attrelid, a.attnum) FROM pg_attribute a "
                f"WHERE a.attrelid = '{table}'::regclass AND a.attname = '{column}'"
            )).scalar()
            assert comment, f"{table}.{column} has no column comment"


def test_full_column_comment_coverage_for_pre_s0_tables():
    """Regression guard for the whole set, not just the sample: every column on every
    pre-S0 table must have a comment (the migration's own count: 281, plus 1 for
    reference_code.valid_from added by the historize-reference-codes migration)."""
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    tables = "', '".join(_SAMPLE_COLUMN_PER_TABLE)
    with eng.connect() as c:
        total, commented = c.execute(text(
            f"""
            SELECT
                count(*),
                count(*) FILTER (WHERE col_description(c.oid, a.attnum) IS NOT NULL)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname IN ('{tables}')
              AND a.attnum > 0 AND NOT a.attisdropped
            """
        )).one()
    assert total == 282, f"expected 282 columns across the 18 pre-S0 tables, found {total}"
    assert commented == total, f"only {commented}/{total} columns have a comment"
