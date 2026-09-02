"""Shared pytest fixtures for ai-timo test suite."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def session_audit_db(tmp_path_factory):
    """Redirect all TestClient lifespans to a temp audit DB for the whole session."""
    db_path = tmp_path_factory.mktemp("audit") / "test_audit.duckdb"
    os.environ["AI_TIMO_AUDIT_DB"] = str(db_path)
    state_path = tmp_path_factory.mktemp("state") / "test_element_states.yaml"
    os.environ["AI_TIMO_ELEMENT_STATE"] = str(state_path)
    dq_scores_path = tmp_path_factory.mktemp("dq") / "test_dq_scores.yaml"
    os.environ["AI_TIMO_DQ_SCORES"] = str(dq_scores_path)
    # Pin the element-lifecycle backend to YAML for the whole suite so tests stay
    # deterministic regardless of the LIVE project.yaml flag (which is now 'postgres'
    # after the Phase-5b.1 cutover). Tests that exercise the Postgres path override
    # this per-test via monkeypatch.setenv("ADIRRA_ELEMENT_BACKEND", "postgres").
    os.environ["ADIRRA_ELEMENT_BACKEND"] = "yaml"
    # Same for the Reference Data (per-code) backend (Phase 5b.2). Default 'yaml' keeps
    # the legacy inline-meanings path; the Postgres per-code tests override per-test.
    os.environ["ADIRRA_REFDATA_BACKEND"] = "yaml"
    return db_path


@pytest.fixture()
def tmp_audit_store(tmp_path):
    """Isolated AuditStore for unit tests (no app context)."""
    from core.audit import AuditStore, set_current_store
    store = AuditStore(tmp_path / "unit_audit.duckdb")
    set_current_store(store)
    yield store
    store.close()


@pytest.fixture()
def client(session_audit_db):
    """TestClient with app lifespan; audit DB redirected to tmp path."""
    from api.main import app
    with TestClient(app) as c:
        yield c
