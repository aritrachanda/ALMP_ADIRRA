"""Phase 7 tests for the Postgres-backed source catalog repository layer
(core.catalog_db.repository).

Runs against a throwaway ``adm_test`` database on the same container. If Postgres is not
reachable, the whole module is skipped so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run catalog DB tests",
                allow_module_level=True)


_TABLES = (
    "catalog_element_snapshot", "catalog_dataset_snapshot", "catalog_refresh_event",
    "catalog_element", "catalog_dataset", "catalog_source",
    "catalog_column_annotation", "catalog_table_annotation",
)


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


@pytest.fixture(autouse=True)
def _clean_tables():
    from sqlalchemy import text
    eng = gdb.get_engine(_TEST_DSN)
    with eng.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


# ── fixtures ─────────────────────────────────────────────────────────────────

def _sample_schemas(row_count_a=100, null_count_a=5):
    return [
        {
            "name": "public",
            "tables": [
                {
                    "schema_name": "public", "table_name": "accounts",
                    "description": "Accounts table",
                    "row_count": row_count_a, "primary_key": ["id"],
                    "columns": [
                        {"name": "id", "data_type": "integer", "null_count": 0, "distinct_count": row_count_a},
                        {"name": "balance", "data_type": "numeric", "null_count": null_count_a, "numeric_avg": 42.5},
                    ],
                },
                {
                    "schema_name": "public", "table_name": "customers",
                    "description": "Customers table",
                    "row_count": 50, "primary_key": ["id"],
                    "columns": [
                        {"name": "id", "data_type": "integer", "null_count": 0, "distinct_count": 50},
                        {"name": "name", "data_type": "text", "null_count": 1},
                    ],
                },
            ],
        }
    ]


def _save(name="acme", schemas=None):
    from core.catalog_db.repository import save_catalog
    save_catalog(
        name, kind="source", connector_type="duckdb", connection_ref="acme_conn",
        version=1, schema_hash="abc123", generated_at=datetime.now(timezone.utc),
        schemas=schemas if schemas is not None else _sample_schemas(),
    )


# ── read shape ───────────────────────────────────────────────────────────────

def test_save_and_load_shape():
    _save()
    from core.catalog_db.repository import load_catalog
    cat = load_catalog("acme", "source")
    assert cat["source"] == "acme"
    assert cat["version"] == 1
    schema_names = [s["name"] for s in cat["schemas"]]
    assert schema_names == ["public"]
    tables = {t["table_name"]: t for t in cat["schemas"][0]["tables"]}
    assert set(tables) == {"accounts", "customers"}
    assert tables["accounts"]["row_count"] == 100
    assert {c["name"] for c in tables["accounts"]["columns"]} == {"id", "balance"}
    # flat columns list mirrors the nested structure, one entry per column
    assert len(cat["columns"]) == 4
    assert all(c["source"] == "acme" for c in cat["columns"])


def test_load_missing_source_returns_empty_dict():
    from core.catalog_db.repository import load_catalog
    assert load_catalog("does-not-exist", "source") == {}


def test_annotation_merge():
    """Annotations are Postgres-backed since Slice F -- seed via AnnotationRepo directly
    (the legacy YAML-file overlay this test wrote to disk no longer exists)."""
    _save()
    from core.annotation_repo import AnnotationRepo
    AnnotationRepo(dsn=_TEST_DSN).save("acme", {
        "version": 1, "dataset": "acme",
        "annotations": {
            "public.accounts": {
                "columns": {"balance": {"user_description": "Steward-written description"}},
            },
        },
    })
    from core.catalog_db.repository import load_catalog
    # catalog_dir just needs to be truthy to opt load_catalog into merging annotations --
    # the value itself is ignored now that annotations are Postgres-only (Slice F).
    cat = load_catalog("acme", "source", catalog_dir=Path("unused"))
    tables = {t["table_name"]: t for t in cat["schemas"][0]["tables"]}
    balance_col = next(c for c in tables["accounts"]["columns"] if c["name"] == "balance")
    assert balance_col["user_description"] == "Steward-written description"
    # unrelated column/table untouched
    id_col = next(c for c in tables["accounts"]["columns"] if c["name"] == "id")
    assert "user_description" not in id_col


# ── single-table upsert isolation ────────────────────────────────────────────

def test_single_table_upsert_isolation():
    _save()
    from core.catalog_db.repository import upsert_table_profile, load_catalog

    before = load_catalog("acme", "source")
    tables_before = {t["table_name"]: t for t in before["schemas"][0]["tables"]}
    assert tables_before["customers"].get("profiled_at") is None

    upsert_table_profile(
        "acme", "public", "accounts",
        {"row_count": 200, "columns": [{"name": "id"}, {"name": "balance", "null_count": 9}]},
        kind="source",
    )

    after = load_catalog("acme", "source")
    tables_after = {t["table_name"]: t for t in after["schemas"][0]["tables"]}
    assert tables_after["accounts"]["row_count"] == 200
    # sibling table completely untouched
    assert tables_after["customers"] == tables_before["customers"]


def test_single_table_upsert_bumps_source_generated_at():
    """A single-table (or bulk per-table) refresh must move the source-level
    'Profiled' timestamp, not just the dataset's own profiled_at — mirroring the
    YAML branch's _write_table_profile_yaml, which already bumps the catalog's
    top-level generated_at on every table write."""
    stale = datetime.now(timezone.utc) - timedelta(days=30)
    from core.catalog_db.repository import save_catalog
    save_catalog(
        "acme", kind="source", connector_type="duckdb", connection_ref="acme_conn",
        version=1, schema_hash="abc123", generated_at=stale, schemas=_sample_schemas(),
    )
    from core.catalog_db.repository import upsert_table_profile, load_catalog

    before = load_catalog("acme", "source")
    assert before["generated_at"] == stale.isoformat()

    upsert_table_profile(
        "acme", "public", "accounts",
        {"row_count": 200, "columns": [{"name": "id"}]},
        kind="source",
    )

    after = load_catalog("acme", "source")
    assert after["generated_at"] != before["generated_at"]
    assert datetime.fromisoformat(after["generated_at"]) > stale


# ── snapshot dedupe + refresh-event logging ──────────────────────────────────

def test_snapshot_dedupe_and_refresh_event_always_logged():
    _save()
    from core.catalog_db.repository import upsert_table_profile
    from core.glossary_db.models import CatalogDatasetSnapshot, CatalogRefreshEvent, CatalogDataset, CatalogSource
    from sqlalchemy import select

    profile_v1 = {"row_count": 100, "columns": [{"name": "id"}, {"name": "balance"}]}
    profile_v2 = {"row_count": 150, "columns": [{"name": "id"}, {"name": "balance"}]}  # changed

    # 1st refresh: establishes baseline snapshot
    upsert_table_profile("acme", "public", "accounts", profile_v1, kind="source", triggered_by="test")
    # 2nd refresh: identical stats -> no new snapshot, but a refresh_event still logs
    upsert_table_profile("acme", "public", "accounts", profile_v1, kind="source", triggered_by="test")
    # 3rd refresh: changed stats -> new snapshot appended
    upsert_table_profile("acme", "public", "accounts", profile_v2, kind="source", triggered_by="test")

    with gdb.session_scope(_TEST_DSN) as s:
        source = s.execute(select(CatalogSource).where(CatalogSource.source_name == "acme")).scalar_one()
        dataset = s.execute(
            select(CatalogDataset).where(
                CatalogDataset.source_id == source.source_id, CatalogDataset.table_name == "accounts"
            )
        ).scalar_one()
        snaps = s.execute(
            select(CatalogDatasetSnapshot).where(CatalogDatasetSnapshot.dataset_id == dataset.dataset_id)
        ).scalars().all()
        events = s.execute(
            select(CatalogRefreshEvent).where(CatalogRefreshEvent.dataset_id == dataset.dataset_id)
            .order_by(CatalogRefreshEvent.refreshed_at)
        ).scalars().all()

    assert len(snaps) == 2  # baseline (v1) + changed (v2); the identical 2nd refresh added none
    assert len(events) == 3  # one per refresh attempt, regardless of whether stats changed
    assert [e.changed for e in events] == [True, False, True]


def test_snapshot_retention_prunes_middle_keeps_first_and_latest():
    """Directly exercises _prune_snapshots (the retention rule) with a small limit,
    rather than driving 50+ real refreshes through upsert_table_profile."""
    _save()
    from core.catalog_db.repository import _prune_snapshots
    from core.glossary_db.models import CatalogDatasetSnapshot, CatalogDataset, CatalogSource
    from sqlalchemy import select

    with gdb.session_scope(_TEST_DSN) as s:
        source = s.execute(select(CatalogSource).where(CatalogSource.source_name == "acme")).scalar_one()
        dataset = s.execute(
            select(CatalogDataset).where(
                CatalogDataset.source_id == source.source_id, CatalogDataset.table_name == "accounts"
            )
        ).scalar_one()
        dataset_id = dataset.dataset_id
        # Insert 10 synthetic snapshots with distinct fingerprints AND explicit, strictly
        # increasing captured_at timestamps — Postgres's now() resolves to transaction start
        # time, so relying on the column default would make every row's timestamp identical
        # within this one transaction and the ordering non-deterministic.
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for i in range(10):
            s.add(CatalogDatasetSnapshot(
                dataset_id=dataset_id, fingerprint=f"fp-{i}",
                schema_name="public", table_name="accounts", row_count=i,
                captured_at=base + timedelta(minutes=i),
            ))
        s.flush()
        _prune_snapshots(s, CatalogDatasetSnapshot, "dataset_id", dataset_id, max_records=5)
        s.flush()
        remaining = s.execute(
            select(CatalogDatasetSnapshot).where(CatalogDatasetSnapshot.dataset_id == dataset_id)
            .order_by(CatalogDatasetSnapshot.captured_at)
        ).scalars().all()

    assert len(remaining) == 5
    # oldest (baseline, row_count=0) survives
    assert remaining[0].row_count == 0
    # the 4 most recent (row_count 6,7,8,9) survive alongside it
    assert {r.row_count for r in remaining} == {0, 6, 7, 8, 9}
