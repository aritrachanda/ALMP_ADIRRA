"""Tests for Catalogs API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_list_sources(client: TestClient):
    resp = client.get("/catalogs/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "sources"
    assert isinstance(body["catalogs"], list)


def test_list_targets(client: TestClient):
    resp = client.get("/catalogs/targets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "targets"


def test_get_catalog(client: TestClient):
    resp = client.get("/catalogs/sources/banking")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("source") == "banking"
    assert "schemas" in body


def test_get_table(client: TestClient):
    resp = client.get("/catalogs/sources/banking/accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table_name"] == "accounts"
    assert "columns" in body


def test_get_missing_catalog(client: TestClient):
    resp = client.get("/catalogs/sources/nonexistent")
    assert resp.status_code == 404


def test_get_missing_table(client: TestClient):
    resp = client.get("/catalogs/sources/banking/nonexistent")
    assert resp.status_code == 404
