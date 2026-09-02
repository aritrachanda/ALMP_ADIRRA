"""S0 foundations — Postgres-backend-resilience guard (govern-pg-s0-foundations, task 3.6).

Covers core.shared.db_availability.require_reachable directly, plus an end-to-end check that
a catalog route returns the clean 503 (via api/main.py's DatabaseUnavailableError handler)
instead of a raw exception when catalog_backend=postgres and the database is unreachable —
and stays completely unaffected in yaml mode. A real-Postgres success case is also covered,
skipped if the database isn't actually reachable in this environment.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.shared.db_availability import DatabaseUnavailableError, require_reachable


# ── unit-level: require_reachable itself ────────────────────────────────────

def test_require_reachable_noop_when_backend_is_yaml():
    require_reachable(lambda: "yaml", "Catalog")  # must not raise, must not even check health


def test_require_reachable_raises_when_postgres_and_unhealthy(monkeypatch):
    monkeypatch.setattr("core.glossary_db.db.health", lambda: False)
    with pytest.raises(DatabaseUnavailableError) as exc_info:
        require_reachable(lambda: "postgres", "Catalog")
    assert exc_info.value.service_label == "Catalog"


def test_require_reachable_passes_when_postgres_and_healthy(monkeypatch):
    monkeypatch.setattr("core.glossary_db.db.health", lambda: True)
    require_reachable(lambda: "postgres", "Catalog")  # must not raise


# ── end-to-end: a real catalog route through the registered exception handler ──

def test_catalog_route_returns_clean_503_when_postgres_unreachable(monkeypatch):
    monkeypatch.setenv("ADIRRA_CATALOG_BACKEND", "postgres")
    monkeypatch.setattr("core.glossary_db.db.health", lambda: False)
    from api.main import app
    with TestClient(app) as c:
        resp = c.get("/catalogs/sources/Kaggle")
    assert resp.status_code == 503
    assert "Catalog database is not running" in resp.json()["detail"]
    assert "docker compose" in resp.json()["detail"]


def test_catalog_route_unaffected_in_yaml_mode(monkeypatch):
    monkeypatch.setenv("ADIRRA_CATALOG_BACKEND", "yaml")
    # Even if health() would report unreachable, yaml mode must never call it.
    monkeypatch.setattr("core.glossary_db.db.health", lambda: (_ for _ in ()).throw(
        AssertionError("health() must not be called in yaml mode")))
    from api.main import app
    with TestClient(app) as c:
        resp = c.get("/catalogs/sources/Kaggle")
    assert resp.status_code == 200


def test_catalog_route_succeeds_when_postgres_reachable(monkeypatch):
    from core.glossary_db.db import health as _health
    if not _health():
        pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run this test")
    monkeypatch.setenv("ADIRRA_CATALOG_BACKEND", "postgres")
    from api.main import app
    with TestClient(app) as c:
        resp = c.get("/catalogs/sources/Kaggle")
    assert resp.status_code == 200
