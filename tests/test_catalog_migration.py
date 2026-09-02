"""Phase 7 tests for the YAML -> Postgres migration + parity script
(core.catalog_db.migrate_from_yaml), run against small fixture catalogs rather than the
real repo data.

Runs against a throwaway ``adm_test`` database on the same container. If Postgres is not
reachable, the whole module is skipped so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os
from datetime import date

import pytest
import yaml

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run catalog migration tests",
                allow_module_level=True)


_TABLES = (
    "catalog_element_snapshot", "catalog_dataset_snapshot", "catalog_refresh_event",
    "catalog_element", "catalog_dataset", "catalog_source",
)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
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


@pytest.fixture(autouse=True)
def _clean_tables():
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    with eng.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


def _write_fixture_catalog(tmp_path, name: str = "fixture_src") -> None:
    """Write a small YAML catalog with real date objects in top_values — replicating the
    real profiler output shape that originally exposed the JSONB date-serialization bug
    (Phase 5, Issue 3/4/6)."""
    catalog = {
        "version": 2,
        "source": name,
        "connection": "fixture_conn",
        "generated_at": "2026-01-01T00:00:00",
        "schema_hash": "deadbeef",
        "schemas": [
            {
                "name": "public",
                "tables": [
                    {
                        "schema_name": "public", "table_name": "orders",
                        "description": "Orders fixture table",
                        "row_count": 10, "primary_key": ["id"], "duplicate_count": 1,
                        "columns": [
                            {"name": "id", "data_type": "integer", "null_count": 0, "distinct_count": 10},
                            {
                                "name": "order_date", "data_type": "date", "null_count": 0,
                                "top_values": [
                                    {"value": date(2024, 1, 1), "count": 3},
                                    {"value": date(2024, 2, 2), "count": 2},
                                ],
                                "numeric_avg": 12.5,
                            },
                        ],
                    },
                ],
            }
        ],
    }
    (tmp_path / f"{name}.yaml").write_text(
        yaml.safe_dump(catalog, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _project(tmp_path) -> dict:
    return {"paths": {"source_catalogs": str(tmp_path)}}


def test_migrate_and_parity_pass(tmp_path):
    _write_fixture_catalog(tmp_path)
    from core.catalog_db.migrate_from_yaml import migrate_one

    migrated, mismatches = migrate_one("fixture_src", "source", _project(tmp_path), force=False)
    assert migrated is True
    assert mismatches == []  # dates + all fields round-trip identically


def test_migrate_skips_without_force_then_reruns_with_force(tmp_path):
    _write_fixture_catalog(tmp_path)
    from core.catalog_db.migrate_from_yaml import migrate_one

    migrated1, _ = migrate_one("fixture_src", "source", _project(tmp_path), force=False)
    assert migrated1 is True

    migrated2, mismatches2 = migrate_one("fixture_src", "source", _project(tmp_path), force=False)
    assert migrated2 is False  # already migrated, no --force -> skipped
    assert mismatches2 == []

    migrated3, mismatches3 = migrate_one("fixture_src", "source", _project(tmp_path), force=True)
    assert migrated3 is True  # --force allows re-run
    assert mismatches3 == []


def test_check_parity_detects_real_mismatch(tmp_path):
    _write_fixture_catalog(tmp_path)
    from core.catalog_db.migrate_from_yaml import migrate_one, check_parity
    from core.catalog_db.repository import upsert_table_profile

    migrate_one("fixture_src", "source", _project(tmp_path), force=False)
    # Diverge Postgres from the original YAML — parity must now report a mismatch.
    upsert_table_profile("fixture_src", "public", "orders", {"row_count": 99999, "columns": []}, kind="source")

    mismatches = check_parity("fixture_src", "source", _project(tmp_path))
    assert any("row_count" in m for m in mismatches)


def test_check_parity_missing_yaml_reports_not_found(tmp_path):
    from core.catalog_db.migrate_from_yaml import check_parity
    mismatches = check_parity("no-such-fixture", "source", _project(tmp_path))
    assert len(mismatches) == 1
    assert "not found" in mismatches[0]
