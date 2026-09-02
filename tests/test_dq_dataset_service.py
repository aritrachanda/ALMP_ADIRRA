"""Tests for the dataset roll-up path of core.dq_service (§15 / §16.4).

Proves the service gathers persisted column records, rolls them up, persists a
dataset record under ``dataset_key``, serves it from the store on re-read, and
re-rolls it when a member column changes (a descope event). The store is the
cache; the constituent column fingerprints are the invalidation key.

Runs against a throwaway ``adm_test`` database on the same container -- DQScoreStore and the
CONTENT half of ElementStateStore (assessment scope) are Postgres-only since Slice F of the
governance YAML->Postgres migration, so this module needs the same pg-gate/isolation scaffolding
as the *_repo.py tests, even though it exercises the service layer rather than a repo directly.
The whole module is skipped if Postgres isn't reachable.
"""
from __future__ import annotations

import os

import pytest

from core import governance_events
from core.audit import events as audit_events
from core.dq_config import DQScoringConfig
from core.dq_dataset_scorer import DATASET_BREAKDOWN_VERSION
from core.dq_score_store import DQScoreStore
from core.dq_service import DQScoringService
from core.element_state import ElementStateStore
from core.glossary_db import db as gdb
from core.semantic_type_store import SemanticTypeStore

CONFIG = DQScoringConfig.from_project()

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"

_SRC = "dqdstest"  # unique source prefix so this module's rows are cheap to isolate/clean


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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run DQ dataset service tests",
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
    """dq_score/element_assessment_scope/semantic_type_assignment rows persist in adm_test
    across runs -- clear this module's test keys before and after each test.
    dq_score_history/element_definition_history cascade-delete via their FKs."""
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScore, ElementAssessmentScope, ElementDefinition, SemanticTypeAssignment

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(DqScore).where(DqScore.key.like(f"{_SRC}%")))
            s.execute(delete(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like(f"{_SRC}%")))
            s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.like(f"{_SRC}%")))
            s.execute(delete(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like(f"{_SRC}%")))

    _wipe()
    yield
    _wipe()


_TBL = {
    "table_name": "t",
    "row_count": 10000,
    "primary_key": [],
    "columns": [
        {"name": "cpty", "data_type": "VARCHAR", "row_count": 10000, "null_count": 0,
         "distinct_count": 8000, "uniqueness_pct": 0.8, "empty_string_count": 0,
         "placeholder_count": 0, "top_values": [{"value": "x", "count": 10}]},
        {"name": "amt", "data_type": "DECIMAL", "row_count": 10000, "null_count": 50,
         "distinct_count": 9000, "uniqueness_pct": 0.9, "empty_string_count": 0,
         "placeholder_count": 0, "numeric_stddev": 100.0,
         "top_values": [{"value": "1", "count": 5}]},
    ],
}


def _service(tmp_path):
    dq_store = DQScoreStore(tmp_path / "dq.yaml")
    element_state = ElementStateStore(tmp_path / "es.yaml")
    semantic_store = SemanticTypeStore(tmp_path / "st.yaml")

    def _col_loader(s, sc, t, c):
        col = next((x for x in _TBL["columns"] if x["name"] == c), None)
        return (dict(col), dict(_TBL)) if col else None

    def _ds_loader(s, sc, t):
        return dict(_TBL)

    service = DQScoringService(
        dq_store=dq_store, element_state=element_state, semantic_store=semantic_store,
        config=CONFIG, column_loader=_col_loader, dataset_loader=_ds_loader,
    )
    return service, dq_store, element_state


def test_score_and_persist_dataset_writes_record(tmp_path):
    service, dq_store, _es = _service(tmp_path)
    record = service.score_and_persist_dataset(_SRC, "sc", "t")
    assert record["state"] == "scored"
    assert record["dq_score"] is not None
    key = dq_store.dataset_key(_SRC, "sc", "t")
    assert dq_store.latest(key)["dq_score"] == record["dq_score"]
    assert record["breakdown_version"] == DATASET_BREAKDOWN_VERSION


def test_get_or_score_dataset_is_read_cached(tmp_path):
    service, dq_store, _es = _service(tmp_path)
    key = dq_store.dataset_key(_SRC, "sc", "t")
    first = service.get_or_score_dataset(_SRC, "sc", "t")
    assert len(dq_store.history(key)) == 1
    second = service.get_or_score_dataset(_SRC, "sc", "t")
    assert second["dq_score"] == first["dq_score"]
    assert len(dq_store.history(key)) == 1  # served from store, no new record


def test_descope_event_rerolls_dataset(tmp_path):
    governance_events.clear()
    try:
        service, dq_store, element_state = _service(tmp_path)
        service.register_subscribers()
        key = dq_store.dataset_key(_SRC, "sc", "t")

        service.score_and_persist_dataset(_SRC, "sc", "t")
        assert len(dq_store.history(key)) == 1

        # Descope a member column → column event → dataset re-roll (its
        # fingerprint set changes, so a new dataset record is appended).
        element_state.set_assessment_scope(_SRC, "sc", "t", "amt", "out_of_scope")
        governance_events.emit(audit_events.ASSESSMENT_SCOPE_CHANGED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "amt",
            "new_scope": "out_of_scope",
        })
        history = dq_store.history(key)
        assert len(history) == 2  # dataset re-rolled after the member change
        assert dq_store.latest(key)["column_count"] == 1  # only cpty remains in scope
    finally:
        governance_events.clear()


def test_fully_descoped_dataset_is_unscored(tmp_path):
    service, dq_store, element_state = _service(tmp_path)
    element_state.set_assessment_scope(_SRC, "sc", "t", "cpty", "out_of_scope")
    element_state.set_assessment_scope(_SRC, "sc", "t", "amt", "out_of_scope")
    record = service.score_and_persist_dataset(_SRC, "sc", "t")
    assert record["state"] == "unscored"
    assert record["reason"] == "fully_descoped"


def test_dataset_history_is_chronological(tmp_path):
    governance_events.clear()
    try:
        service, dq_store, element_state = _service(tmp_path)
        service.register_subscribers()
        service.score_and_persist_dataset(_SRC, "sc", "t")

        element_state.set_assessment_scope(_SRC, "sc", "t", "amt", "out_of_scope")
        governance_events.emit(audit_events.ASSESSMENT_SCOPE_CHANGED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "amt",
            "new_scope": "out_of_scope",
        })
        trend = service.dataset_history(_SRC, "sc", "t")
        assert len(trend) == 2
        # Oldest → newest (store keeps latest first; history() reverses it).
        assert all("scored_at" in rec for rec in trend)
        assert trend[0]["scored_at"] <= trend[1]["scored_at"]
    finally:
        governance_events.clear()
