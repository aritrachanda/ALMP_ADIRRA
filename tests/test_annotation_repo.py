"""govern-pg-e-annotations -- AnnotationRepo (Postgres) + core.annotations backend-branch tests.

Runs against a throwaway ``adm_test`` database on the same container; the whole module is
skipped if Postgres isn't reachable, so the rest of the suite still runs anywhere.
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
        eng = gdb.get_engine(_BASE_DSN)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run annotation tests",
                allow_module_level=True)


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
    cfg = Config("db/alembic.ini")
    command.upgrade(cfg, "head")

    yield

    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import CatalogColumnAnnotation, CatalogTableAnnotation

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(CatalogColumnAnnotation).where(
                CatalogColumnAnnotation.element_key.like("antest%")))
            s.execute(delete(CatalogTableAnnotation).where(
                CatalogTableAnnotation.dataset_key.like("antest%")))

    _wipe()
    yield
    _wipe()


@pytest.fixture()
def repo():
    from core.annotation_repo import AnnotationRepo
    return AnnotationRepo(dsn=_TEST_DSN)


def test_load_returns_empty_shape_for_unknown_dataset(repo):
    result = repo.load("antest_nope")
    assert result == {"version": 1, "dataset": "antest_nope", "annotations": {}}


def test_save_then_load_roundtrips_table_and_column_content(repo):
    data = {
        "version": 1,
        "dataset": "antest_banking",
        "annotations": {
            "src.derivatives": {
                "user_description": "Derivative contracts.",
                "mapping_instructions": "Map to target derivatives table.",
                "columns": {
                    "derivative_id": {"user_description": "Unique id.", "mapping_instructions": "Preserve exact value."},
                    "notional": {"user_description": "Contract notional amount."},
                },
            }
        },
    }
    repo.save("antest_banking", data)

    loaded = repo.load("antest_banking")
    assert loaded["dataset"] == "antest_banking"
    table = loaded["annotations"]["src.derivatives"]
    assert table["user_description"] == "Derivative contracts."
    assert table["mapping_instructions"] == "Map to target derivatives table."
    assert table["columns"]["derivative_id"] == {
        "user_description": "Unique id.", "mapping_instructions": "Preserve exact value."
    }
    assert table["columns"]["notional"] == {"user_description": "Contract notional amount."}


def test_table_with_no_recorded_schema_round_trips_its_leading_dot_key(repo):
    """A real annotation file can have a table entry with no schema recorded at all —
    get_table_annotations' own key construction (f"{schema}.{table}") never special-cases
    that, so the key genuinely looks like ".bank_accounts". load() must reproduce this
    exact key, not silently drop the leading dot (found via a real parity mismatch during
    the Slice E migration, 2026-08-17)."""
    data = {
        "version": 1, "dataset": "antest_noschema",
        "annotations": {".bank_accounts": {"user_description": "No schema on this one."}},
    }
    repo.save("antest_noschema", data)

    loaded = repo.load("antest_noschema")
    assert loaded["annotations"] == {".bank_accounts": {"user_description": "No schema on this one."}}


def test_table_with_only_column_annotations_reconstructs_without_a_table_row(repo):
    """A table with no description of its own (only column-level content) must still round-trip
    — the outer key comes back purely from the column rows, no empty table row is created."""
    data = {
        "version": 1,
        "dataset": "antest_faker",
        "annotations": {
            "public.accounts": {
                "columns": {"account_id": {"user_description": "The account's own id."}},
            }
        },
    }
    repo.save("antest_faker", data)

    loaded = repo.load("antest_faker")
    table = loaded["annotations"]["public.accounts"]
    assert "user_description" not in table
    assert "mapping_instructions" not in table
    assert table["columns"]["account_id"] == {"user_description": "The account's own id."}


def test_save_reconciles_removed_entries(repo):
    """Saving a smaller dict than before must delete the rows that dropped out — matching the
    YAML file's own full-rewrite semantics, not just accumulate forever."""
    first = {
        "version": 1, "dataset": "antest_shrink",
        "annotations": {
            "s.t1": {"user_description": "Table one.", "columns": {"a": {"user_description": "Col a."}}},
            "s.t2": {"user_description": "Table two."},
        },
    }
    repo.save("antest_shrink", first)
    assert set(repo.load("antest_shrink")["annotations"].keys()) == {"s.t1", "s.t2"}

    second = {"version": 1, "dataset": "antest_shrink", "annotations": {"s.t1": {"user_description": "Table one."}}}
    repo.save("antest_shrink", second)

    loaded = repo.load("antest_shrink")
    assert set(loaded["annotations"].keys()) == {"s.t1"}
    assert "columns" not in loaded["annotations"]["s.t1"]


def test_pure_helpers_work_unchanged_on_a_postgres_sourced_dict(repo):
    """get_table_annotations/set_table_annotations are plain dict helpers with no I/O — they
    must behave identically whether the dict came from YAML or from AnnotationRepo.load()."""
    from core.annotations import get_table_annotations, set_table_annotations

    repo.save("antest_helpers", {
        "version": 1, "dataset": "antest_helpers",
        "annotations": {"s.t": {"user_description": "Existing.", "columns": {}}},
    })
    data = repo.load("antest_helpers")

    before = get_table_annotations(data, "s", "t")
    assert before["user_description"] == "Existing."

    set_table_annotations(data, "s", "t", user_description="Updated.", mapping_instructions=None,
                          column_annotations={"c1": {"user_description": "Col one.", "mapping_instructions": None}})
    repo.save("antest_helpers", data)

    reloaded = repo.load("antest_helpers")
    after = get_table_annotations(reloaded, "s", "t")
    assert after["user_description"] == "Updated."
    assert after["columns"]["c1"]["user_description"] == "Col one."


# ── core.annotations (always Postgres, since Slice F) ────────────────────────

def test_core_annotations_load_and_save_go_straight_to_postgres():
    """`catalog_dir` is accepted (and ignored) for call-site compatibility only -- there is no
    yaml branch anymore, so this proves load_annotations/save_annotations round-trip through
    Postgres with no flag/env var involved at all."""
    from core.annotations import load_annotations, save_annotations, set_table_annotations

    data = load_annotations("antest_flagbranch", catalog_dir=None)
    assert data == {"version": 1, "dataset": "antest_flagbranch", "annotations": {}}

    set_table_annotations(data, "s", "t", user_description="Via core.annotations.",
                          mapping_instructions=None, column_annotations={})
    result = save_annotations("antest_flagbranch", None, data)
    assert result is None

    reloaded = load_annotations("antest_flagbranch")
    assert reloaded["annotations"]["s.t"]["user_description"] == "Via core.annotations."

