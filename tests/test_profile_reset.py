"""add-profile-reset, Section 1 — the dummy-source fixture.

Seeds ~10 columns of a throwaway ``profile_reset_dummy_source`` table into every one of the
seven Postgres-backed stores the reset feature touches (catalog, semantic types, DQ scores,
Interpretation lifecycle + content, Reference Data per-code review, reference-set binding +
its review lifecycle, and catalog annotations) via each store's REAL write path — never
hand-rolled SQL. This is the baseline the reset orchestrator (built in later sections) is
verified against, and this file's own sanity-check test proves every store's write path still
works before any reset logic is written.

Runs against a throwaway ``adm_test`` database on the same Postgres container, same pattern as
``tests/test_dq_score_repo.py``: the whole module is skipped if Postgres isn't reachable.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from core.dq_config import DQScoringConfig
from core.glossary_db import db as gdb

CONFIG = DQScoringConfig.from_project()

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"

# ── dummy source shape ───────────────────────────────────────────────────────────────────────
DUMMY_SOURCE = "profile_reset_dummy_source"
DUMMY_SCHEMA = "dummy"
DUMMY_TABLE = "dummy_table"
DUMMY_REFSET_ID = "profile_reset_dummy_set"

#: 10 columns spanning a realistic mix of types/roles so every store has something to hold.
DUMMY_COLUMNS = [
    "customer_id", "status_code", "amount", "created_date", "email",
    "country_code", "notes", "is_active", "risk_score", "last_login",
]
_DATA_TYPES = {
    "customer_id": "BIGINT", "status_code": "VARCHAR", "amount": "DECIMAL(18,2)",
    "created_date": "DATE", "email": "VARCHAR", "country_code": "VARCHAR",
    "notes": "VARCHAR", "is_active": "BOOLEAN", "risk_score": "DOUBLE",
    "last_login": "TIMESTAMP",
}
CODED_COLUMN = "status_code"          # bound to a reference set + per-code review
REF_CODES = ["A", "B", "C"]


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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run profile-reset tests",
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


def _breakdown(score: int, *, state: str = "scored") -> dict:
    return {"state": state, "dq_score": score, "grade_label": "Good", "components": [],
            "breakdown_version": 1}


# ── seed helpers — one per store, each via that store's real write path ─────────────────────

def _seed_catalog() -> None:
    from core.catalog_db import save_catalog

    now = datetime.now(timezone.utc)
    columns = [
        {
            "name": name,
            "ordinal": i,
            "data_type": _DATA_TYPES[name],
            "description": f"Auto-seeded description for {name}.",
            "row_count": 1000,
            "null_count": 5,
            "null_pct": 0.5,
            "distinct_count": 42,
            "sample_values": ["sample_a", "sample_b"],
        }
        for i, name in enumerate(DUMMY_COLUMNS)
    ]
    schemas = [{
        "name": DUMMY_SCHEMA,
        "tables": [{
            "schema_name": DUMMY_SCHEMA,
            "table_name": DUMMY_TABLE,
            "description": "Dummy table seeded for add-profile-reset testing.",
            "row_count": 1000,
            "primary_key": ["customer_id"],
            "foreign_keys": [],
            "relations": [],
            "duplicate_count": 0,
            "duplicate_pct": 0.0,
            "orphan_fk_count": 0,
            "completeness_summary": 0.95,
            "pct_columns_described": 1.0,
            "columns": columns,
        }],
    }]
    save_catalog(
        DUMMY_SOURCE, kind="source", connector_type="duckdb", connection_ref=DUMMY_SOURCE,
        version=2, schema_hash="dummyhash0000", generated_at=now, schemas=schemas,
    )


def _seed_semantic_types() -> None:
    from core.semantic_type_repo import SemanticTypeRepo

    repo = SemanticTypeRepo(dsn=_TEST_DSN)
    for column in DUMMY_COLUMNS:
        repo.set_proposed(
            source=DUMMY_SOURCE, schema=DUMMY_SCHEMA, table=DUMMY_TABLE, column=column,
            type_id="free_text", domain_role="attribute", confidence=0.6, resolver_source="rule",
        )
    # Accept one, so governance has genuinely progressed past "proposed" for at least one column.
    repo.accept(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, DUMMY_COLUMNS[0],
                accepted_by="test-steward", type_id="free_text", domain_role="attribute")


def _seed_dq_scores() -> None:
    from core.dq_score_repo import DQScoreRepo

    repo = DQScoreRepo(dsn=_TEST_DSN)
    for column in DUMMY_COLUMNS:
        key = repo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, column)
        repo.record(key, _breakdown(78), signal_snapshot={"col": column}, config=CONFIG)
    dataset_key = repo.dataset_key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    repo.record(dataset_key, _breakdown(80), signal_snapshot={"dataset": True}, config=CONFIG)


def _seed_interpretation() -> None:
    from core.element_content_repo import ElementContentRepo
    from core.element_lifecycle_repo import ElementLifecycleRepo, make_key

    content = ElementContentRepo(dsn=_TEST_DSN)
    lifecycle = ElementLifecycleRepo(dsn=_TEST_DSN)
    for column in DUMMY_COLUMNS:
        content.set_description(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, column,
                                 f"Seeded definition for {column}.")
        content.set_business_name(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, column,
                                   column.replace("_", " ").title())
        lifecycle.save(make_key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, column),
                       has_content=True, actor="test-steward")
    lifecycle.submit(make_key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, DUMMY_COLUMNS[0]),
                      actor="test-steward")
    content.set_data_story(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE,
                           tagline="One row per customer.",
                           narrative="Seeded dataset story for profile-reset testing.")
    content.set_assessment_scope(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, DUMMY_COLUMNS[0],
                                 "in_scope", scoped_by="test-steward")


def _seed_reference_data() -> None:
    from core.dq_score_repo import DQScoreRepo
    from core.reference_code_repo import ReferenceCodeRepo

    element_key = DQScoreRepo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, CODED_COLUMN)
    repo = ReferenceCodeRepo(dsn=_TEST_DSN)
    edits = [{"code": code, "value": code, "meaning": f"Meaning of {code}", "origin": "profiled"}
             for code in REF_CODES]
    repo.save_codes(element_key, edits, actor="test-steward")
    repo.submit_codes(element_key, actor="test-steward")


def _seed_reference_set_binding() -> None:
    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope
    from core.reference_binding_review_repo import ReferenceBindingReviewRepo
    from core.reference_set_repo import ReferenceSetRepo
    from core.shared.models import ReferenceSet, ReferenceSetEntry

    # Reference sets are hand-authored/read-only through the app (ReferenceSetRepo has no
    # create-set method) — this fixture creates its own tiny throwaway set directly via the
    # ORM models, which is legitimate for test setup, mirroring how a real set would already
    # exist in a non-empty database.
    with session_scope(_TEST_DSN) as s:
        ref_set = ReferenceSet(set_id=DUMMY_REFSET_ID, name="Dummy Status Codes", kind="local",
                               status="approved")
        s.add(ref_set)
        s.flush()
        for code in REF_CODES:
            s.add(ReferenceSetEntry(reference_set_id=ref_set.id, code=code, value=code,
                                    meaning=f"Meaning of {code}", status="active"))

    element_key = DQScoreRepo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, CODED_COLUMN)
    ReferenceSetRepo(dsn=_TEST_DSN).set_binding(element_key, DUMMY_REFSET_ID)
    ReferenceBindingReviewRepo(dsn=_TEST_DSN).submit(element_key, actor="test-steward")


def _seed_annotations() -> None:
    from core.annotation_repo import AnnotationRepo

    repo = AnnotationRepo(dsn=_TEST_DSN)
    data = {
        "version": 1,
        "dataset": DUMMY_SOURCE,
        "annotations": {
            f"{DUMMY_SCHEMA}.{DUMMY_TABLE}": {
                "user_description": "Seeded table annotation.",
                "columns": {
                    DUMMY_COLUMNS[0]: {
                        "user_description": f"Seeded column annotation for {DUMMY_COLUMNS[0]}.",
                    },
                },
            },
        },
    }
    repo.save(DUMMY_SOURCE, data)


def _wipe_dummy_source() -> None:
    """Best-effort teardown across every store this fixture writes to.

    Deleting the "current"/parent row cascades to its own history table — every history FK in
    ``core/shared/models/governance.py`` is ``ON DELETE CASCADE`` — and deleting the
    ``reference_set``/``catalog_source`` parent rows cascades their whole child tree
    (entries + binding; datasets + elements + snapshots + refresh events), so only these
    top-level deletes are needed.
    """
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import (
        CatalogColumnAnnotation, CatalogSource, CatalogTableAnnotation, DatasetStory, DqScore,
        ElementAssessmentScope, ElementDefinition, LifecycleTransition, ReferenceCode,
        ReferenceSet, ReviewSubject, SemanticTypeAssignment,
    )

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        s.execute(delete(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{prefix}%")))
        s.execute(delete(DqScore).where(DqScore.key.like(f"{prefix}%")))
        s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.like(f"{prefix}%")))
        s.execute(delete(DatasetStory).where(DatasetStory.dataset_key.like(f"{prefix}%")))
        s.execute(delete(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like(f"{prefix}%")))
        s.execute(delete(ReferenceCode).where(ReferenceCode.element_key.like(f"{prefix}%")))
        s.execute(delete(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{prefix}%")))
        s.execute(delete(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%")))
        s.execute(delete(LifecycleTransition).where(LifecycleTransition.subject_ref.like(f"{prefix}%")))
        s.execute(delete(ReviewSubject).where(ReviewSubject.subject_ref.like(f"{prefix}%")))
        s.execute(delete(ReferenceSet).where(ReferenceSet.set_id == DUMMY_REFSET_ID))
        s.execute(delete(CatalogSource).where(CatalogSource.source_name == DUMMY_SOURCE))


@pytest.fixture()
def seeded_dummy_source():
    """Seed the dummy source into every affected store, yield, then wipe it clean."""
    _wipe_dummy_source()
    _seed_catalog()
    _seed_semantic_types()
    _seed_dq_scores()
    _seed_interpretation()
    _seed_reference_data()
    _seed_reference_set_binding()
    _seed_annotations()
    yield
    _wipe_dummy_source()


# ── seed sanity check (task 1.3) ─────────────────────────────────────────────────────────────

def test_seed_populates_every_affected_store(seeded_dummy_source):
    from sqlalchemy import select

    from core.glossary_db.db import session_scope
    from core.shared.models import (
        CatalogColumnAnnotation, CatalogDataset, CatalogElement, CatalogSource,
        CatalogTableAnnotation, DatasetStory, DqScore, ElementAssessmentScope,
        ElementDefinition, ElementReferenceBinding, ReferenceCode, ReferenceSet,
        ReviewSubject, SemanticTypeAssignment,
    )

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == DUMMY_SOURCE)
        ).scalar_one()
        dataset = s.execute(
            select(CatalogDataset).where(CatalogDataset.source_id == source.source_id)
        ).scalar_one()
        elements = s.execute(
            select(CatalogElement).where(CatalogElement.dataset_id == dataset.dataset_id)
        ).scalars().all()
        assert len(elements) == len(DUMMY_COLUMNS)
        assert all(e.row_count is not None for e in elements)   # profiled, not blank
        assert all(e.data_type for e in elements)

        semantic_rows = s.execute(
            select(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(semantic_rows) == len(DUMMY_COLUMNS)
        assert any(r.accepted_at is not None for r in semantic_rows)

        dq_rows = s.execute(
            select(DqScore).where(DqScore.key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(dq_rows) == len(DUMMY_COLUMNS) + 1            # +1 dataset-level rollup

        def_rows = s.execute(
            select(ElementDefinition).where(ElementDefinition.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(def_rows) == len(DUMMY_COLUMNS)
        assert all(r.definition and r.business_name for r in def_rows)

        story = s.execute(
            select(DatasetStory).where(DatasetStory.dataset_key == f"{DUMMY_SOURCE}|{DUMMY_SCHEMA}|{DUMMY_TABLE}")
        ).scalar_one_or_none()
        assert story is not None

        scope_rows = s.execute(
            select(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(scope_rows) == 1

        code_rows = s.execute(
            select(ReferenceCode).where(ReferenceCode.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(code_rows) == len(REF_CODES)

        ref_set = s.execute(
            select(ReferenceSet).where(ReferenceSet.set_id == DUMMY_REFSET_ID)
        ).scalar_one_or_none()
        assert ref_set is not None
        binding = s.execute(
            select(ElementReferenceBinding).where(ElementReferenceBinding.element_key.like(f"{prefix}%"))
        ).scalar_one_or_none()
        assert binding is not None

        table_anno = s.execute(
            select(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%"))
        ).scalar_one_or_none()
        assert table_anno is not None
        col_annos = s.execute(
            select(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(col_annos) == 1

        # Interpretation lifecycle + reference-binding review both register as review subjects.
        subjects = s.execute(
            select(ReviewSubject).where(ReviewSubject.subject_ref.like(f"{prefix}%"))
        ).scalars().all()
        assert len(subjects) >= 2


# ── Section 2.1a — catalog_db.clear_table_stats/clear_source_stats regression tests ──────────

def test_clear_table_stats_preserves_identity_and_nulls_profiling_derived(seeded_dummy_source):
    from sqlalchemy import select

    from core.catalog_db.repository import NOT_PROFILED_STATUS, clear_table_stats
    from core.glossary_db.db import session_scope
    from core.shared.models import CatalogDataset, CatalogElement, CatalogSource

    with session_scope(_TEST_DSN) as s:
        result = clear_table_stats(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result == {"dataset": 1, "element": len(DUMMY_COLUMNS)}

    with session_scope(_TEST_DSN) as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == DUMMY_SOURCE)
        ).scalar_one()
        dataset = s.execute(
            select(CatalogDataset).where(CatalogDataset.source_id == source.source_id)
        ).scalar_one()
        # Onboarding-owned fields survive unchanged.
        assert dataset.description == "Dummy table seeded for add-profile-reset testing."
        assert dataset.primary_key == ["customer_id"]
        assert dataset.foreign_keys == []
        assert dataset.relations == []
        # Profiling-derived fields are cleared.
        assert dataset.row_count is None
        assert dataset.completeness_summary is None
        assert dataset.profiling_status == NOT_PROFILED_STATUS
        assert dataset.profiled_at is None

        elements = s.execute(
            select(CatalogElement).where(CatalogElement.dataset_id == dataset.dataset_id)
        ).scalars().all()
        assert len(elements) == len(DUMMY_COLUMNS)
        by_name = {e.column_name: e for e in elements}
        for name in DUMMY_COLUMNS:
            el = by_name[name]
            # Column identity survives.
            assert el.data_type == _DATA_TYPES[name]
            assert el.description == f"Auto-seeded description for {name}."
            # Profiling-derived stats are cleared.
            assert el.row_count is None
            assert el.null_count is None
            assert el.distinct_count is None
            assert el.sample_values is None


def test_clear_table_stats_is_idempotent(seeded_dummy_source):
    from core.catalog_db.repository import clear_table_stats
    from core.glossary_db.db import session_scope

    with session_scope(_TEST_DSN) as s:
        clear_table_stats(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    with session_scope(_TEST_DSN) as s:
        result = clear_table_stats(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result == {"dataset": 0, "element": 0}


def test_clear_source_stats_clears_every_table_and_source_generated_at(seeded_dummy_source):
    from sqlalchemy import select

    from core.catalog_db.repository import clear_source_stats
    from core.glossary_db.db import session_scope
    from core.shared.models import CatalogSource

    with session_scope(_TEST_DSN) as s:
        result = clear_source_stats(s, DUMMY_SOURCE)
    assert result == {"dataset": 1, "element": len(DUMMY_COLUMNS)}

    with session_scope(_TEST_DSN) as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == DUMMY_SOURCE)
        ).scalar_one()
        assert source.generated_at is None


# ── Section 2.2 — semantic_type_repo.clear_for_table/clear_for_source ────────────────────────

def test_semantic_type_clear_for_table_soft_resets(seeded_dummy_source):
    from sqlalchemy import select

    from core.glossary_db.db import session_scope
    from core.semantic_type_repo import SemanticTypeRepo
    from core.shared.models import SemanticTypeAssignment

    repo = SemanticTypeRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared == len(DUMMY_COLUMNS)

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(rows) == len(DUMMY_COLUMNS)      # soft reset — rows still exist (D9)
        for row in rows:
            assert row.type_id == "unresolved"
            assert row.accepted_at is None
            assert row.system_deduced_type is None

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_semantic_type_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.glossary_db.db import session_scope
    from core.semantic_type_repo import SemanticTypeRepo

    repo = SemanticTypeRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == len(DUMMY_COLUMNS)


# ── Section 2.3 — dq_score_repo.clear_for_table/clear_for_source ─────────────────────────────

def test_dq_score_clear_for_table_soft_resets(seeded_dummy_source):
    from sqlalchemy import select

    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScore, DqScoreHistory

    repo = DQScoreRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared == len(DUMMY_COLUMNS) + 1     # +1 dataset rollup

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(select(DqScore).where(DqScore.key.like(f"{prefix}%"))).scalars().all()
        assert len(rows) == len(DUMMY_COLUMNS) + 1   # soft reset — rows still exist (D9)
        for row in rows:
            assert row.state == "unscored"
            assert row.dq_score is None

        history = s.execute(
            select(DqScoreHistory).where(DqScoreHistory.key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(history) == len(DUMMY_COLUMNS) + 1   # the "scored" version closed into history
        assert all(h.state == "scored" for h in history)

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_dq_score_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope

    repo = DQScoreRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == len(DUMMY_COLUMNS) + 1


# ── Section 2.4 — element_lifecycle_repo.clear_for_table/clear_for_source ────────────────────

def test_element_lifecycle_clear_for_table_resets_to_empty(seeded_dummy_source):
    from sqlalchemy import select

    from core.element_lifecycle_repo import ElementLifecycleRepo
    from core.glossary_db.db import session_scope
    from core.shared.models import ReviewSubject

    repo = ElementLifecycleRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, actor="tester")
    assert cleared == len(DUMMY_COLUMNS)   # every seeded column was saved to 'draft'

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        subjects = s.execute(
            select(ReviewSubject).where(
                ReviewSubject.subject_type == "element_interpretation",
                ReviewSubject.subject_ref.like(f"{prefix}%"),
            )
        ).scalars().all()
        assert len(subjects) == len(DUMMY_COLUMNS)   # soft reset — subjects still exist
        assert all(s.current_state == "empty" for s in subjects)

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_element_lifecycle_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.element_lifecycle_repo import ElementLifecycleRepo
    from core.glossary_db.db import session_scope

    repo = ElementLifecycleRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == len(DUMMY_COLUMNS)


# ── Section 2.5 — element_content_repo.clear_for_table/clear_for_source ──────────────────────

def test_element_content_clear_for_table_soft_resets_definitions_hard_deletes_story_and_scope(
    seeded_dummy_source,
):
    from sqlalchemy import select

    from core.element_content_repo import ElementContentRepo
    from core.glossary_db.db import session_scope
    from core.shared.models import DatasetStory, ElementAssessmentScope, ElementDefinition

    repo = ElementContentRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        result = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result == {"definitions": len(DUMMY_COLUMNS), "story": 1, "scopes": 1}

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        defs = s.execute(
            select(ElementDefinition).where(ElementDefinition.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert len(defs) == len(DUMMY_COLUMNS)   # soft reset — rows still exist
        assert all(d.definition is None and d.business_name is None for d in defs)

        story = s.execute(
            select(DatasetStory).where(DatasetStory.dataset_key == f"{DUMMY_SOURCE}|{DUMMY_SCHEMA}|{DUMMY_TABLE}")
        ).scalar_one_or_none()
        assert story is None    # hard-deleted

        scopes = s.execute(
            select(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like(f"{prefix}%"))
        ).scalars().all()
        assert scopes == []     # hard-deleted

    with session_scope(_TEST_DSN) as s:
        result_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result_again == {"definitions": 0, "story": 0, "scopes": 0}


def test_element_content_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.element_content_repo import ElementContentRepo
    from core.glossary_db.db import session_scope

    repo = ElementContentRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        result = repo.clear_for_source(s, DUMMY_SOURCE)
    assert result == {"definitions": len(DUMMY_COLUMNS), "story": 1, "scopes": 1}


# ── Section 2.6 — reference_code_repo.clear_for_table/clear_for_source ───────────────────────

def test_reference_code_clear_for_table_resets_to_empty(seeded_dummy_source):
    from sqlalchemy import select

    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope
    from core.reference_code_repo import ReferenceCodeRepo
    from core.shared.models import ReferenceCode, ReferenceCodeHistory

    element_key = DQScoreRepo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, CODED_COLUMN)
    repo = ReferenceCodeRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared == len(REF_CODES)

    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(ReferenceCode).where(ReferenceCode.element_key == element_key)
        ).scalars().all()
        assert len(rows) == len(REF_CODES)     # soft reset — rows still exist
        for row in rows:
            assert row.status == "empty"
            assert row.value is None
            assert row.meaning is None
        # None of the seeded codes were ever approved, so no history window should exist.
        history = s.execute(
            select(ReferenceCodeHistory).where(ReferenceCodeHistory.element_key == element_key)
        ).scalars().all()
        assert history == []

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_reference_code_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.glossary_db.db import session_scope
    from core.reference_code_repo import ReferenceCodeRepo

    repo = ReferenceCodeRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == len(REF_CODES)


# ── Section 2.7 — reference_set_repo.clear_for_table/clear_for_source (bindings) ─────────────

def test_reference_set_binding_clear_for_table_hard_deletes(seeded_dummy_source):
    from sqlalchemy import select

    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope
    from core.reference_set_repo import ReferenceSetRepo
    from core.shared.models import ElementReferenceBinding

    element_key = DQScoreRepo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, CODED_COLUMN)
    repo = ReferenceSetRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared == 1

    with session_scope(_TEST_DSN) as s:
        binding = s.execute(
            select(ElementReferenceBinding).where(ElementReferenceBinding.element_key == element_key)
        ).scalar_one_or_none()
        assert binding is None     # hard-deleted

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_reference_set_binding_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.glossary_db.db import session_scope
    from core.reference_set_repo import ReferenceSetRepo

    repo = ReferenceSetRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == 1


# ── Section 2.8 — reference_binding_review_repo.clear_for_table/clear_for_source ─────────────

def test_reference_binding_review_clear_for_table_hard_deletes(seeded_dummy_source):
    from sqlalchemy import select

    from core.dq_score_repo import DQScoreRepo
    from core.glossary_db.db import session_scope
    from core.reference_binding_review_repo import ReferenceBindingReviewRepo
    from core.shared.models import ReviewSubject

    element_key = DQScoreRepo.key(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, CODED_COLUMN)
    repo = ReferenceBindingReviewRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared == 1

    with session_scope(_TEST_DSN) as s:
        subj = s.execute(
            select(ReviewSubject).where(
                ReviewSubject.subject_type == "reference_binding",
                ReviewSubject.subject_ref == element_key,
            )
        ).scalar_one_or_none()
        assert subj is None    # hard-deleted

    with session_scope(_TEST_DSN) as s:
        cleared_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert cleared_again == 0


def test_reference_binding_review_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.glossary_db.db import session_scope
    from core.reference_binding_review_repo import ReferenceBindingReviewRepo

    repo = ReferenceBindingReviewRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        cleared = repo.clear_for_source(s, DUMMY_SOURCE)
    assert cleared == 1


# ── Section 2.9 — annotation_repo.clear_for_table/clear_for_source ───────────────────────────

def test_annotation_clear_for_table_hard_deletes(seeded_dummy_source):
    from sqlalchemy import select

    from core.annotation_repo import AnnotationRepo
    from core.glossary_db.db import session_scope
    from core.shared.models import CatalogColumnAnnotation, CatalogTableAnnotation

    repo = AnnotationRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        result = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result == {"table": 1, "columns": 1}

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        assert s.execute(
            select(CatalogTableAnnotation).where(CatalogTableAnnotation.dataset_key.like(f"{prefix}%"))
        ).first() is None
        assert s.execute(
            select(CatalogColumnAnnotation).where(CatalogColumnAnnotation.element_key.like(f"{prefix}%"))
        ).first() is None

    with session_scope(_TEST_DSN) as s:
        result_again = repo.clear_for_table(s, DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result_again == {"table": 0, "columns": 0}


def test_annotation_clear_for_source_matches_clear_for_table(seeded_dummy_source):
    from core.annotation_repo import AnnotationRepo
    from core.glossary_db.db import session_scope

    repo = AnnotationRepo(dsn=_TEST_DSN)
    with session_scope(_TEST_DSN) as s:
        result = repo.clear_for_source(s, DUMMY_SOURCE)
    assert result == {"table": 1, "columns": 1}


# ── Section 3 — core/profile_reset.py orchestrator ────────────────────────────────────────────

def test_is_profiled_reflects_catalog_state(seeded_dummy_source):
    from core.catalog_db import is_profiled

    assert is_profiled(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE) is True
    assert is_profiled(DUMMY_SOURCE, DUMMY_SCHEMA, "no_such_table") is False
    assert is_profiled("no_such_source", DUMMY_SCHEMA, DUMMY_TABLE) is False


def test_reset_table_clears_every_store_and_is_idempotent(seeded_dummy_source):
    from core.catalog_db import is_profiled
    from core.profile_reset import reset_table

    result = reset_table(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result["columns"] == len(DUMMY_COLUMNS)
    assert result["dq_score"] == len(DUMMY_COLUMNS) + 1
    assert result["semantic_type"] == len(DUMMY_COLUMNS)
    assert result["reference_code"] == len(REF_CODES)
    assert result["reference_set_binding"] == 1
    assert result["reference_binding_review"] == 1
    assert result["interpretation_lifecycle"] == len(DUMMY_COLUMNS)
    assert result["interpretation_content"] == {"definitions": len(DUMMY_COLUMNS), "story": 1, "scopes": 1}
    assert result["annotations"] == {"table": 1, "columns": 1}
    assert result["catalog"] == {"dataset": 1, "element": len(DUMMY_COLUMNS)}
    assert is_profiled(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE) is False

    # Idempotent — every underlying clear_for_table already guarantees zero on a second call.
    result_again = reset_table(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)
    assert result_again["dq_score"] == 0
    assert result_again["semantic_type"] == 0
    assert result_again["reference_code"] == 0
    assert result_again["reference_set_binding"] == 0
    assert result_again["reference_binding_review"] == 0
    assert result_again["interpretation_lifecycle"] == 0
    assert result_again["interpretation_content"] == {"definitions": 0, "story": 0, "scopes": 0}
    assert result_again["annotations"] == {"table": 0, "columns": 0}
    assert result_again["catalog"] == {"dataset": 0, "element": 0}


def test_reset_table_emits_progress_for_every_step(seeded_dummy_source):
    from core.profile_reset import STEPS, reset_table

    seen: list[str] = []
    reset_table(
        DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE,
        on_progress=lambda step, detail: seen.append(step),
    )
    assert seen == list(STEPS)


def test_reset_source_matches_reset_table_for_a_single_table_source(seeded_dummy_source):
    from core.profile_reset import reset_source

    result = reset_source(DUMMY_SOURCE)
    assert result["table_count"] == 1
    assert len(result["tables"]) == 1
    table_result = result["tables"][0]
    assert table_result["dq_score"] == len(DUMMY_COLUMNS) + 1
    assert table_result["catalog"] == {"dataset": 1, "element": len(DUMMY_COLUMNS)}


def test_reset_table_rolls_back_everything_on_failure(seeded_dummy_source, monkeypatch):
    from sqlalchemy import select

    from core.annotation_repo import AnnotationRepo
    from core.glossary_db.db import session_scope
    from core.profile_reset import reset_table
    from core.shared.models import DqScore, SemanticTypeAssignment

    def _boom(self, session, source, schema, table):
        raise RuntimeError("simulated annotation-store failure")

    # Annotations run AFTER dq_score/semantic_type in STEPS, so if the rollback is real, those
    # earlier stores' successful-looking writes must ALSO be undone.
    monkeypatch.setattr(AnnotationRepo, "clear_for_table", _boom)

    with pytest.raises(RuntimeError, match="simulated annotation-store failure"):
        reset_table(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE)

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        dq_rows = s.execute(select(DqScore).where(DqScore.key.like(f"{prefix}%"))).scalars().all()
        assert all(r.state == "scored" for r in dq_rows)     # untouched — rolled back

        sem_rows = s.execute(
            select(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{prefix}%"))
        ).scalars().all()
        assert all(r.type_id == "free_text" for r in sem_rows)   # untouched — rolled back


def test_reset_table_logs_one_audit_event(seeded_dummy_source, tmp_audit_store):
    from core.profile_reset import reset_table

    reset_table(DUMMY_SOURCE, DUMMY_SCHEMA, DUMMY_TABLE, actor="tester")
    events = tmp_audit_store.list_events(event_type="profile_reset")
    assert len(events) == 1
    assert events[0]["subject_id"] == f"{DUMMY_SOURCE}|{DUMMY_SCHEMA}|{DUMMY_TABLE}"


# ── Section 4 — SSE API endpoints in api/routes/discovery.py ─────────────────────────────────

def _parse_sse(body: str) -> list[tuple[str, dict]]:
    import json as _json_mod

    frames: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        event = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if event and data:
            frames.append((event, _json_mod.loads(data)))
    return frames


@pytest.fixture()
def api_client():
    from fastapi.testclient import TestClient

    from api.main import app
    with TestClient(app) as c:
        yield c


def test_reset_table_endpoint_streams_progress_and_clears(seeded_dummy_source, api_client):
    from core.profile_reset import STEPS

    resp = api_client.post(f"/discovery/{DUMMY_SOURCE}/{DUMMY_SCHEMA}.{DUMMY_TABLE}/reset")
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert frames[0][0] == "started"
    assert frames[-1][0] == "done"
    steps_seen = [f[1]["step"] for f in frames if f[0] == "progress"]
    assert steps_seen == list(STEPS)
    result = frames[-1][1]["result"]
    assert result["catalog"] == {"dataset": 1, "element": len(DUMMY_COLUMNS)}
    assert result["dq_score"] == len(DUMMY_COLUMNS) + 1


def test_reset_source_endpoint_streams_progress_and_clears(seeded_dummy_source, api_client):
    resp = api_client.post(f"/discovery/{DUMMY_SOURCE}/reset")
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert frames[0][0] == "started"
    assert frames[-1][0] == "done"
    result = frames[-1][1]["result"]
    assert result["table_count"] == 1
    assert result["tables"][0]["catalog"] == {"dataset": 1, "element": len(DUMMY_COLUMNS)}


def test_reset_table_endpoint_reports_rollback_on_failure(seeded_dummy_source, api_client, monkeypatch):
    from sqlalchemy import select

    from core.annotation_repo import AnnotationRepo
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScore

    def _boom(self, session, source, schema, table):
        raise RuntimeError("simulated annotation-store failure")

    monkeypatch.setattr(AnnotationRepo, "clear_for_table", _boom)

    resp = api_client.post(f"/discovery/{DUMMY_SOURCE}/{DUMMY_SCHEMA}.{DUMMY_TABLE}/reset")
    assert resp.status_code == 200     # the SSE stream itself succeeds — the failure is IN it
    frames = _parse_sse(resp.text)
    assert frames[-1][0] == "error"
    assert frames[-1][1]["rolled_back"] is True

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(select(DqScore).where(DqScore.key.like(f"{prefix}%"))).scalars().all()
        assert all(r.state == "scored" for r in rows)   # untouched — rolled back


def test_wipe_leaves_no_trace(seeded_dummy_source):
    """Proves the teardown itself is complete — the baseline the reset tests will diff against."""
    from sqlalchemy import select

    from core.glossary_db.db import session_scope
    from core.shared.models import (
        CatalogSource, DqScore, ElementDefinition, ReferenceCode, ReferenceSet,
        ReviewSubject, SemanticTypeAssignment,
    )

    _wipe_dummy_source()

    prefix = f"{DUMMY_SOURCE}|"
    with session_scope(_TEST_DSN) as s:
        assert s.execute(
            select(CatalogSource).where(CatalogSource.source_name == DUMMY_SOURCE)
        ).scalar_one_or_none() is None
        assert s.execute(select(DqScore).where(DqScore.key.like(f"{prefix}%"))).first() is None
        assert s.execute(
            select(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{prefix}%"))
        ).first() is None
        assert s.execute(
            select(ElementDefinition).where(ElementDefinition.element_key.like(f"{prefix}%"))
        ).first() is None
        assert s.execute(
            select(ReferenceCode).where(ReferenceCode.element_key.like(f"{prefix}%"))
        ).first() is None
        assert s.execute(
            select(ReferenceSet).where(ReferenceSet.set_id == DUMMY_REFSET_ID)
        ).first() is None
        assert s.execute(
            select(ReviewSubject).where(ReviewSubject.subject_ref.like(f"{prefix}%"))
        ).first() is None
