"""Tests for Annotations API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_get_annotations(client: TestClient):
    resp = client.get("/annotations/banking")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("dataset") == "banking"
    assert "annotations" in body


def test_set_and_get_annotations(client: TestClient):
    body = {
        "user_description": "Test table description",
        "mapping_instructions": "Map carefully",
        "columns": {
            "account_id": {
                "user_description": "Unique account ID",
                "mapping_instructions": "Direct map",
            }
        },
    }
    resp = client.put("/annotations/banking/src.accounts", json=body)
    assert resp.status_code == 200

    # Read back
    resp = client.get("/annotations/banking")
    assert resp.status_code == 200
    annotations = resp.json()
    table_ann = annotations.get("annotations", {}).get("src.accounts", {})
    assert table_ann.get("user_description") == "Test table description"
