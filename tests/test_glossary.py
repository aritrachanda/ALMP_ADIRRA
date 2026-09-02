"""Tests for Glossary API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_get_glossary(client: TestClient):
    resp = client.get("/glossary")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_crud_term(client: TestClient):
    # Create
    term = {
        "title": "__test_term__",
        "domain": "Test",
        "category": "Test",
        "business_description": "A test term",
    }
    resp = client.put("/glossary/terms", json=term)
    assert resp.status_code == 200
    created = resp.json()
    term_id = created["id"]
    assert created["title"] == "__test_term__"

    # Read
    resp = client.get(f"/glossary/terms/{term_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "__test_term__"

    # Update
    created["business_description"] = "Updated description"
    resp = client.put("/glossary/terms", json=created)
    assert resp.status_code == 200
    assert resp.json()["business_description"] == "Updated description"

    # Delete
    resp = client.delete(f"/glossary/terms/{term_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = client.get(f"/glossary/terms/{term_id}")
    assert resp.status_code == 404


def test_uncovered_concepts(client: TestClient):
    resp = client.get("/glossary/uncovered")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_duplicate_title_rejected(client: TestClient):
    term = {"title": "__test_dup_term__", "domain": "Test", "category": "Test"}
    resp = client.put("/glossary/terms", json=term)
    assert resp.status_code == 200
    term_id = resp.json()["id"]
    try:
        # Same title (different case/whitespace) must be rejected as a duplicate, not
        # silently accepted with a suffixed id.
        resp = client.put("/glossary/terms", json={"title": "  __TEST_DUP_TERM__  "})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]
    finally:
        client.delete(f"/glossary/terms/{term_id}")
