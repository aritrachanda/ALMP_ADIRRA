"""govern-pg-c1-element-content-build -- ElementContentRepo (Postgres) + ElementStateStore
content-branch tests.

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run element content tests",
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


@pytest.fixture()
def repo():
    from core.element_content_repo import ElementContentRepo
    return ElementContentRepo(dsn=_TEST_DSN)


@pytest.fixture(autouse=True)
def _clean_rows():
    """Rows persist in adm_test across runs -- clear this module's test keys first.
    element_definition_history cascade-deletes via its FK."""
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import DatasetStory, ElementAssessmentScope, ElementDefinition

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.like("ctest%")))
            s.execute(delete(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like("ctest%")))
            s.execute(delete(DatasetStory).where(DatasetStory.dataset_key.like("ctest%")))

    _wipe()
    yield
    _wipe()


def _src(name: str) -> str:
    return f"ctest_{name}"


# ── definition + business name ────────────────────────────────────────────────


def test_missing_content_returns_none(repo):
    source = _src("missing")
    assert repo.get_description(source, "s", "t", "c") is None
    assert repo.get_business_name(source, "s", "t", "c") is None
    assert repo.get_metadata(source, "s", "t", "c") == {}


def test_definition_round_trips_with_ai_flag(repo):
    source = _src("def")
    repo.set_description(source, "s", "t", "c", "The account's closing balance.", is_ai_generated=True)

    assert repo.get_description(source, "s", "t", "c") == "The account's closing balance."
    assert repo.get_metadata(source, "s", "t", "c")["is_ai_generated"] is True


def test_business_name_round_trips_independently(repo):
    """Definition and business name live on one row but carry SEPARATE AI flags -- writing one
    must not disturb the other's flag."""
    source = _src("bn")
    repo.set_description(source, "s", "t", "c", "A definition.", is_ai_generated=True)
    repo.set_business_name(source, "s", "t", "c", "Closing Balance", is_ai_generated=False)

    meta = repo.get_metadata(source, "s", "t", "c")
    assert repo.get_business_name(source, "s", "t", "c") == "Closing Balance"
    assert meta["is_ai_generated"] is True          # definition still AI
    assert meta["business_name_is_ai"] is False     # business name is human


def test_editing_clears_the_ai_flag(repo):
    """A human editing an AI-written definition flips its flag -- the AI marker must not stick."""
    source = _src("edit")
    repo.set_description(source, "s", "t", "c", "AI wrote this.", is_ai_generated=True)
    repo.set_description(source, "s", "t", "c", "A person rewrote this.", is_ai_generated=False)

    assert repo.get_metadata(source, "s", "t", "c")["is_ai_generated"] is False


def test_set_metadata_ignores_fields_owned_by_other_slices(repo):
    """Reference-data keys belong to other slices -- they must not be silently stored here."""
    source = _src("meta")
    repo.set_description(source, "s", "t", "c", "d")
    repo.set_metadata(source, "s", "t", "c",
                      {"criticality": "critical", "refdata_bound_set_id": "currency_codes"})

    meta = repo.get_metadata(source, "s", "t", "c")
    assert meta["criticality"] == "critical"
    assert "refdata_bound_set_id" not in meta


# ── data story + data grain ───────────────────────────────────────────────────


def test_data_story_round_trips_and_data_grain_is_its_own_field(repo):
    """Data Grain is a real named column now, but is still served as `tagline` so existing
    callers/UI keep working (C1 decision, 2026-08-15)."""
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import DatasetStory

    source = _src("story")
    repo.set_data_story(source, "s", "t", "One row per loan per reporting date.",
                        "Loans outstanding at each month end.", is_ai_generated=True)

    story = repo.get_data_story(source, "s", "t")
    assert story["narrative"] == "Loans outstanding at each month end."
    assert story["tagline"] == "One row per loan per reporting date."
    assert story["is_ai_generated"] is True

    with session_scope(_TEST_DSN) as s:
        row = s.execute(
            select(DatasetStory).where(DatasetStory.dataset_key == repo.dataset_key(source, "s", "t"))
        ).scalar_one()
        assert row.data_grain == "One row per loan per reporting date."  # stored under its real name


def test_data_story_is_dataset_level_not_column_level(repo):
    """The story key has no column component -- two columns of the same table share one story."""
    source = _src("dskey")
    assert repo.dataset_key(source, "s", "t") == f"{source}|s|t"
    assert repo.key(source, "s", "t", "c") == f"{source}|s|t|c"


# ── assessment scope ──────────────────────────────────────────────────────────


def test_assessment_scope_defaults_to_in_scope(repo):
    assert repo.get_assessment_scope(_src("scope"), "s", "t", "c") == "in_scope"


def test_assessment_scope_round_trips(repo):
    source = _src("scope2")
    repo.set_assessment_scope(source, "s", "t", "c", "out_of_scope",
                              scope_reason="platform-technical column", scoped_by="alice")

    assert repo.get_assessment_scope(source, "s", "t", "c") == "out_of_scope"
    record = repo.get_assessment_scope_record(source, "s", "t", "c")
    assert record["scope_reason"] == "platform-technical column"
    assert record["scoped_by"] == "alice"


def test_assessment_scope_rejects_an_invalid_value(repo):
    with pytest.raises(ValueError):
        repo.set_assessment_scope(_src("scope3"), "s", "t", "c", "banana")


# ── history (opens on submission only) ────────────────────────────────────────


def test_no_history_until_submission(repo):
    """Saving repeatedly must NOT create versions -- only submission does (C1 decision)."""
    source = _src("hist1")
    repo.set_description(source, "s", "t", "c", "first")
    repo.set_description(source, "s", "t", "c", "second")
    repo.set_business_name(source, "s", "t", "c", "A Name")

    assert repo.history(source, "s", "t", "c") == []


def test_submission_opens_a_window_with_who_and_when(repo):
    source = _src("hist2")
    repo.set_description(source, "s", "t", "c", "The agreed definition.", is_ai_generated=False)
    repo.set_business_name(source, "s", "t", "c", "Agreed Name")

    repo.record_submission(source, "s", "t", "c", submitted_by="alice")

    hist = repo.history(source, "s", "t", "c")
    assert len(hist) == 1
    assert hist[0]["definition"] == "The agreed definition."
    assert hist[0]["business_name"] == "Agreed Name"
    assert hist[0]["submitted_by"] == "alice"
    assert hist[0]["valid_from"] is not None
    assert hist[0]["valid_to"] is None          # still the current wording


def test_second_submission_closes_the_previous_window(repo):
    """Real SCD2: the earlier wording gets a real end date, exactly where the new one begins."""
    source = _src("hist3")
    repo.set_description(source, "s", "t", "c", "original wording")
    repo.record_submission(source, "s", "t", "c", submitted_by="alice")

    repo.set_description(source, "s", "t", "c", "revised wording")
    repo.record_submission(source, "s", "t", "c", submitted_by="bob")

    hist = repo.history(source, "s", "t", "c")
    assert len(hist) == 2
    assert hist[0]["definition"] == "original wording"
    assert hist[0]["valid_to"] is not None                    # closed
    assert hist[0]["valid_to"] == hist[1]["valid_from"]       # no gap, no overlap
    assert hist[1]["definition"] == "revised wording"
    assert hist[1]["valid_to"] is None                        # the open one


def test_history_preserves_the_ai_flag_of_the_time(repo):
    source = _src("hist4")
    repo.set_description(source, "s", "t", "c", "AI drafted this.", is_ai_generated=True)
    repo.record_submission(source, "s", "t", "c", submitted_by="alice")

    assert repo.history(source, "s", "t", "c")[0]["definition_is_ai"] is True


def test_submission_without_content_raises(repo):
    with pytest.raises(ValueError):
        repo.record_submission(_src("hist5"), "s", "t", "c", submitted_by="alice")


# ── ElementStateStore content methods (always Postgres since Slice F) ────────


def test_store_content_methods_go_to_postgres(tmp_path, monkeypatch):
    from core.element_state import ElementStateStore

    monkeypatch.setenv("ADM_DATABASE_URL", _TEST_DSN)
    store = ElementStateStore(tmp_path / "element_states.yaml")
    source = _src("branch")

    store.set_description(source, "s", "t", "c", "written to postgres", is_ai_generated=True)
    store.set_business_name(source, "s", "t", "c", "Postgres Name")

    assert store.get_description(source, "s", "t", "c") == "written to postgres"
    assert store.get_business_name(source, "s", "t", "c") == "Postgres Name"
    assert store.get_metadata(source, "s", "t", "c")["is_ai_generated"] is True

    store.record_content_submission(source, "s", "t", "c", submitted_by="alice")
    assert len(store.content_history(source, "s", "t", "c")) == 1


def test_content_methods_unaffected_by_element_backend_flag(tmp_path, monkeypatch):
    """Content (Postgres-only since Slice F) and lifecycle (still flag-gated) are independent --
    forcing lifecycle to yaml must not drag content across with it."""
    from core.element_state import ElementStateStore

    monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "yaml")
    monkeypatch.setenv("ADM_DATABASE_URL", _TEST_DSN)
    store = ElementStateStore(tmp_path / "element_states.yaml")
    source = _src("indep")

    store.set_description(source, "s", "t", "c", "still postgres")
    assert store.get_description(source, "s", "t", "c") == "still postgres"
    assert store._use_pg() is False  # lifecycle stayed on yaml

