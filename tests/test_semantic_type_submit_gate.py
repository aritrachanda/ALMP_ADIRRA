"""B1 (govern-pg-b1-semantic-types-build): backend enforcement of the Interpretation Set
submit gate on ``POST /{source}/{table}/{column}/submit`` -- description + business name +
an Accepted semantic type, mirroring the frontend's submitGateMet and the existing
submit_reference_codes 409 precedent.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests._pg_semantic_type_isolation import restore_real_element_definitions, restore_real_semantic_type_rows

_restore_banking_semantic_types = restore_real_semantic_type_rows("banking|")
_restore_banking_definitions = restore_real_element_definitions("banking|")


@pytest.fixture()
def client(tmp_path, monkeypatch, session_audit_db):
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from api.main import app
    with TestClient(app) as c:
        yield c


def _accept_semantic_type(client: TestClient, source: str, table: str, column: str, schema: str) -> None:
    resp = client.post(
        f"/semantic-types/{source}/{table}/{column}/accept?schema={schema}",
        json={"accepted_by": "alice"},
    )
    assert resp.status_code == 200


def _blank_real_description(element_key: str) -> None:
    """These 3 tests run against the real, already-governed `banking` catalog (the submit
    gate needs a real column to exist) -- this column may already carry a real description
    from genuine past use. Temporarily blank it so the gate's own check is truly exercised;
    the module's autouse restore fixture puts the real value back after the test."""
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementDefinition

    with session_scope() as s:
        row = s.query(ElementDefinition).filter(ElementDefinition.element_key == element_key).one_or_none()
        if row is not None:
            row.definition = None


def _unaccept_real_semantic_type(key: str) -> None:
    """Same reasoning as `_blank_real_description`, for a real, already-accepted semantic
    type -- restored automatically by the module's autouse fixture after the test."""
    from core.glossary_db.db import session_scope
    from core.shared.models import SemanticTypeAssignment

    with session_scope() as s:
        row = s.query(SemanticTypeAssignment).filter(SemanticTypeAssignment.key == key).one_or_none()
        if row is not None:
            row.accepted_at = None
            row.accepted_by = None
            row.accepted_by_role = None


def test_submit_without_description_returns_409(client: TestClient):
    _blank_real_description("banking|src|accounts|account_id")
    resp = client.post("/element/banking/accounts/account_id/submit")
    assert resp.status_code == 409


def test_submit_without_semantic_type_accepted_returns_409(client: TestClient):
    _unaccept_real_semantic_type("banking|src|accounts|currency")
    client.patch(
        "/element/banking/accounts/currency/business-name",
        json={"business_name": "Currency"},
    )
    client.patch(
        "/element/banking/accounts/currency/description",
        json={"description": "The transaction currency."},
    )
    resp = client.post("/element/banking/accounts/currency/submit")
    assert resp.status_code == 409


def test_submit_with_full_gate_met_succeeds(client: TestClient):
    source, table, column, schema = "banking", "accounts", "balance", "src"
    client.patch(
        f"/element/{source}/{table}/{column}/business-name",
        json={"business_name": "Account Balance"},
    )
    client.patch(
        f"/element/{source}/{table}/{column}/description",
        json={"description": "The account's current balance."},
    )
    _accept_semantic_type(client, source, table, column, schema)

    resp = client.post(f"/element/{source}/{table}/{column}/submit?schema={schema}")
    assert resp.status_code == 200
    assert resp.json()["submission"]["submitted_at"] is not None
