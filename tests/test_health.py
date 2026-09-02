"""Smoke tests for the FastAPI app — health and readiness endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["boot_id"]  # per-process id clients use to detect a restart


def test_readiness(client: TestClient):
    resp = client.get("/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "project" in body
    assert "provider" in body
