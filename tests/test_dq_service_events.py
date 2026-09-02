"""Tests for core.dq_service — score-on-write and event-triggered re-score.

This is the DoD proof for U2a: a semantic accept on a column visibly changes
the persisted DQ score (verifiable in the store, not the UI).

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
from core.dq_score_store import DQScoreStore
from core.dq_service import DQScoringService
from core.element_state import ElementStateStore
from core.glossary_db import db as gdb
from core.semantic_type_store import SemanticTypeStore

CONFIG = DQScoringConfig.from_project()

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"

_SRC = "dqevttest"  # unique source prefix so this module's rows are cheap to isolate/clean


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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run DQ service event tests",
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


_COL = {
    "name": "cpty", "data_type": "VARCHAR", "row_count": 10000, "null_count": 0,
    "distinct_count": 8000, "uniqueness_pct": 0.8, "empty_string_count": 0,
    "placeholder_count": 0, "top_values": [{"value": "x", "count": 10}],
}


def _service(tmp_path, loader=None):
    dq_store = DQScoreStore(tmp_path / "dq.yaml")
    element_state = ElementStateStore(tmp_path / "es.yaml")
    semantic_store = SemanticTypeStore(tmp_path / "st.yaml")
    loader = loader or (lambda s, sc, t, c: (dict(_COL), None))
    service = DQScoringService(
        dq_store=dq_store, element_state=element_state, semantic_store=semantic_store,
        config=CONFIG, column_loader=loader,
    )
    return service, dq_store, element_state, semantic_store


def test_score_and_persist_writes_record(tmp_path):
    service, dq_store, *_ = _service(tmp_path)
    result = service.score_and_persist(_SRC, "sc", "t", "cpty")
    assert result["state"] == "scored"
    assert result["archetype"] == "free_text"
    assert dq_store.latest(dq_store.key(_SRC, "sc", "t", "cpty"))["dq_score"] == result["dq_score"]


def test_semantic_confirm_rescores_column(tmp_path):
    governance_events.clear()
    try:
        service, dq_store, _es, semantic_store = _service(tmp_path)
        service.register_subscribers()
        key = dq_store.key(_SRC, "sc", "t", "cpty")

        service.score_and_persist(_SRC, "sc", "t", "cpty")
        baseline = dq_store.latest(key)
        assert baseline["archetype"] == "free_text"

        # Accept a semantic type that maps to a different archetype (0b).
        semantic_store.accept(_SRC, "sc", "t", "cpty", accepted_by="tester",
                               type_id="country_code", domain_role="code")
        governance_events.emit(audit_events.SEMANTIC_TYPE_ACCEPTED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
            "type_id": "country_code",
        })

        after = dq_store.latest(key)
        assert after["archetype"] == "coded"
        assert after["dq_score"] != baseline["dq_score"]
        assert len(dq_store.history(key)) == 2
    finally:
        governance_events.clear()


def test_event_handler_is_exception_isolated(tmp_path):
    governance_events.clear()
    try:
        def _broken_loader(s, sc, t, c):
            raise RuntimeError("catalog blew up")

        service, _dq, *_ = _service(tmp_path, loader=_broken_loader)
        service.register_subscribers()
        # Must not raise — a DQ failure never breaks a semantic disposition.
        governance_events.emit(audit_events.SEMANTIC_TYPE_ACCEPTED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
        })
    finally:
        governance_events.clear()


def test_unknown_column_returns_none(tmp_path):
    service, _dq, *_ = _service(tmp_path, loader=lambda s, sc, t, c: None)
    assert service.score_and_persist(_SRC, "sc", "t", "missing") is None


def test_out_of_scope_column_persists_unscored(tmp_path):
    service, dq_store, element_state, _st = _service(tmp_path)
    element_state.set_assessment_scope(_SRC, "sc", "t", "cpty", "out_of_scope")
    result = service.score_and_persist(_SRC, "sc", "t", "cpty")
    assert result["state"] == "unscored"
    assert result["reason"] == "out_of_scope"


def test_scope_change_event_rescores_column(tmp_path):
    """U2c: a scope change re-evaluates the column via the governance event bus.

    Descope → the DQ record becomes ``unscored``; re-scope → scored again. The
    scope event reuses the same event→re-score path as a semantic accept.
    """
    governance_events.clear()
    try:
        service, dq_store, element_state, _st = _service(tmp_path)
        service.register_subscribers()
        key = dq_store.key(_SRC, "sc", "t", "cpty")

        service.score_and_persist(_SRC, "sc", "t", "cpty")
        assert dq_store.latest(key)["state"] == "scored"

        # Descope → event → re-eval → unscored.
        element_state.set_assessment_scope(_SRC, "sc", "t", "cpty", "out_of_scope")
        governance_events.emit(audit_events.ASSESSMENT_SCOPE_CHANGED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
            "new_scope": "out_of_scope",
        })
        after = dq_store.latest(key)
        assert after["state"] == "unscored"
        assert after["reason"] == "out_of_scope"

        # Re-scope → event → re-eval → scored again.
        element_state.set_assessment_scope(_SRC, "sc", "t", "cpty", "in_scope")
        governance_events.emit(audit_events.ASSESSMENT_SCOPE_CHANGED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
            "new_scope": "in_scope",
        })
        assert dq_store.latest(key)["state"] == "scored"
    finally:
        governance_events.clear()


def test_scope_change_event_is_exception_isolated(tmp_path):
    """A DQ failure during a scope re-score must never propagate to the caller."""
    governance_events.clear()
    try:
        def _broken_loader(s, sc, t, c):
            raise RuntimeError("catalog blew up")

        service, *_ = _service(tmp_path, loader=_broken_loader)
        service.register_subscribers()
        # Must not raise — a DQ failure never breaks a scope disposition.
        governance_events.emit(audit_events.ASSESSMENT_SCOPE_CHANGED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
        })
    finally:
        governance_events.clear()



def test_accepted_type_id_joins_signal_fingerprint(tmp_path):
    """The accepted type_id must change the signal fingerprint (cache invalidation)."""
    governance_events.clear()
    try:
        service, dq_store, _es, semantic_store = _service(tmp_path)
        key = dq_store.key(_SRC, "sc", "t", "cpty")
        service.score_and_persist(_SRC, "sc", "t", "cpty")
        fp_before = dq_store.latest(key)["signal_fingerprint"]

        semantic_store.accept(_SRC, "sc", "t", "cpty", accepted_by="tester",
                               type_id="country_code", domain_role="code")
        service.score_and_persist(_SRC, "sc", "t", "cpty")
        fp_after = dq_store.latest(key)["signal_fingerprint"]
        assert fp_before != fp_after
    finally:
        governance_events.clear()


def test_semantic_accept_rescores_with_interpretation_line_item(tmp_path):
    """SD-R3c: a semantic accept re-scores the column and the resulting record's
    Interpretation component gains its Semantic Type line-item (0/7 → 7/7)."""
    governance_events.clear()
    try:
        dq_store = DQScoreStore(tmp_path / "dq.yaml")
        element_state = ElementStateStore(tmp_path / "es.yaml")
        semantic_store = SemanticTypeStore(tmp_path / "st.yaml")
        service = DQScoringService(
            dq_store=dq_store, element_state=element_state, semantic_store=semantic_store,
            config=CONFIG, column_loader=lambda s, sc, t, c: (dict(_COL), None),
        )
        service.register_subscribers()
        key = dq_store.key(_SRC, "sc", "t", "cpty")

        service.score_and_persist(_SRC, "sc", "t", "cpty")
        baseline = dq_store.latest(key)
        # No resolver record yet → the Semantic Type line-item scores 0/7.
        assert "semantic" not in baseline["applicable_components"]

        def _semantic_item(record):
            interp = next(c for c in record["components"] if c["name"] == "interpretation")
            return next(li for li in interp["line_items"] if li["label"] == "Semantic Type")

        assert _semantic_item(baseline)["earned"] == 0.0

        semantic_store.accept(_SRC, "sc", "t", "cpty", accepted_by="tester",
                               type_id="country_code", domain_role="code")
        governance_events.emit(audit_events.SEMANTIC_TYPE_ACCEPTED, {
            "source": _SRC, "schema": "sc", "table": "t", "column": "cpty",
            "type_id": "country_code",
        })

        after = dq_store.latest(key)
        assert _semantic_item(after)["earned"] == 7.0   # accepted → full 7/7
        assert after["dq_score"] != baseline["dq_score"]
    finally:
        governance_events.clear()

