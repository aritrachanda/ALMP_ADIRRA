"""Tests for Business Name endpoints (PATCH + draft)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(session_audit_db):
    from api.main import app
    with TestClient(app) as c:
        yield c


def test_patch_business_name(client: TestClient):
    resp = client.patch(
        "/element/banking/accounts/account_id/business-name",
        json={"business_name": "Account Identifier"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_name"] == "Account Identifier"
    assert body["business_name_is_ai"] is False


def test_patch_business_name_ai_flag(client: TestClient):
    resp = client.patch(
        "/element/banking/accounts/balance/business-name",
        json={"business_name": "Account Balance", "is_ai_generated": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_name"] == "Account Balance"
    assert body["business_name_is_ai"] is True


def test_patch_business_name_persisted(client: TestClient):
    client.patch(
        "/element/banking/accounts/status/business-name",
        json={"business_name": "Account Status Code"},
    )
    resp = client.get("/element/banking/accounts/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_name"] == "Account Status Code"


def test_draft_business_name(client: TestClient):
    resp = client.post(
        "/element/banking/accounts/account_id/draft-business-name",
        json={},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "draft" in body
    assert isinstance(body["draft"], str)
    assert len(body["draft"]) > 0


def test_get_element_returns_default_business_name(client: TestClient):
    """Columns without a stored business name return a title-cased default."""
    resp = client.get("/element/banking/accounts/account_id")
    assert resp.status_code == 200
    body = resp.json()
    assert "business_name" in body
    assert isinstance(body["business_name"], str)
    assert body["business_name"] != ""


def test_patch_business_name_schema_param(client: TestClient):
    resp = client.patch(
        "/element/banking/accounts/account_id/business-name?schema=src",
        json={"business_name": "Schema-qualified Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["business_name"] == "Schema-qualified Name"
