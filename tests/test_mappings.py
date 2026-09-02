"""Tests for Mappings API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_list_mappings(client: TestClient):
    resp = client.get("/mappings")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:
        assert "source" in body[0]
        assert "target" in body[0]


def test_get_mapping(client: TestClient):
    resp = client.get("/mappings/banking/bird")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("source") == "banking"
    assert body.get("target") == "bird"
    assert "tables" in body


def test_get_missing_mapping(client: TestClient):
    resp = client.get("/mappings/nonexistent/nonexistent")
    assert resp.status_code == 404


def test_patch_candidates(client: TestClient):
    # Get current mapping to find a column to update
    resp = client.get("/mappings/banking/bird")
    assert resp.status_code == 200
    mapping = resp.json()
    tbl = mapping["tables"][0]
    col = tbl["columns"][0]

    update = {
        "updates": [{
            "target_schema": tbl["target_schema"],
            "target_table": tbl["target_table"],
            "target_column": col["target_column"],
            "status": "accepted",
        }]
    }
    resp = client.patch("/mappings/banking/bird/candidates", json=update)
    assert resp.status_code == 200

    # Verify the status was updated
    resp2 = client.get("/mappings/banking/bird")
    updated = resp2.json()
    for t in updated["tables"]:
        if t["target_table"] == tbl["target_table"]:
            for c in t["columns"]:
                if c["target_column"] == col["target_column"]:
                    assert c["status"] == "accepted"
                    # Reset back to pending
                    reset = {"updates": [{
                        "target_schema": tbl["target_schema"],
                        "target_table": tbl["target_table"],
                        "target_column": col["target_column"],
                        "status": "pending",
                    }]}
                    client.patch("/mappings/banking/bird/candidates", json=reset)
                    break
