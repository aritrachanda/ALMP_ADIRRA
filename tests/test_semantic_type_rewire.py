from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests._pg_semantic_type_isolation import restore_real_semantic_type_rows

_restore_banking_semantic_types = restore_real_semantic_type_rows("banking|")


@pytest.fixture()
def element_client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from api.main import app

    with TestClient(app) as client:
        yield client, app


def test_table_overview_auto_resolves_blank_store_and_preserves_chart_shape(element_client):
    client, app = element_client

    resp = client.get("/element/banking/accounts/overview?schema=src")
    assert resp.status_code == 200
    body = resp.json()

    mix = body["semantic_type_mix"]
    assert mix
    assert all(set(item.keys()) == {"type", "count", "color"} for item in mix)

    counts = {item["type"]: item["count"] for item in mix}
    assert counts.get("identifier", 0) >= 1
    assert counts.get("coded", 0) >= 1
    assert counts.get("monetary", 0) >= 1
    assert sum(counts.values()) == body["column_count"]

    persisted = app.state.semantic_type_store.find_table("banking", "src", "accounts")
    assert persisted
    assert any(record["type_id"] == "currency_code" for record in persisted)


def test_columns_summary_reports_type_id_and_domain_role(element_client):
    client, _ = element_client

    resp = client.get("/element/banking/accounts/overview?schema=src")
    assert resp.status_code == 200
    currency = next(column for column in resp.json()["columns_summary"] if column["name"] == "currency")

    assert currency["semantic_type"] == "currency_code"
    assert currency["semantic_domain_role"] == "code"


def test_column_detail_reports_type_id_and_domain_role(element_client):
    client, _ = element_client

    resp = client.get("/element/banking/accounts/currency?schema=src")
    assert resp.status_code == 200
    body = resp.json()

    assert body["semantic_type"] == "currency_code"
    assert body["semantic_domain_role"] == "code"
