"""U2b — DQ badge cutover: API tests.

Covers the visible cutover from the retired A/B/C ``quality_grade`` to the DQ
badge on the element, table-overview and table-list responses, plus the
dedicated ``GET /{source}/{table}/{column}/dq`` endpoint (score-present and
score-absent/first-view-populate paths).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(session_audit_db):
    from api.main import app
    with TestClient(app) as c:
        yield c


def _assert_scored_badge(badge: dict) -> None:
    assert badge is not None
    assert badge["state"] == "scored"
    assert isinstance(badge["dq_score"], int)
    assert 0 <= badge["dq_score"] <= 100
    assert badge["grade_label"]
    assert badge["grade_color_intent"]


def test_dq_endpoint_first_view_populates_then_serves(client: TestClient):
    # Score-absent path: first view computes-and-persists.
    resp = client.get("/element/banking/accounts/currency/dq?schema=src")
    assert resp.status_code == 200
    first = resp.json()
    _assert_scored_badge(first)
    assert "components" in first  # full breakdown on the dedicated endpoint

    # Score-present path: second view is served from the store (same score).
    resp2 = client.get("/element/banking/accounts/currency/dq?schema=src")
    assert resp2.status_code == 200
    assert resp2.json()["dq_score"] == first["dq_score"]


def test_dq_endpoint_unknown_column_404(client: TestClient):
    resp = client.get("/element/banking/accounts/not_a_column/dq?schema=src")
    assert resp.status_code == 404


def test_get_element_carries_dq_badge_and_drops_quality_grade(client: TestClient):
    resp = client.get("/element/banking/accounts/currency?schema=src")
    assert resp.status_code == 200
    body = resp.json()
    assert "quality_grade" not in body
    _assert_scored_badge(body["dq"])
    # Element view carries the full component breakdown for the card.
    assert isinstance(body["dq"]["components"], list) and body["dq"]["components"]
    assert body["dq"]["data_score"] is not None
    assert body["dq"]["governance_score"] is not None


def test_table_overview_columns_summary_uses_dq_badge(client: TestClient):
    resp = client.get("/element/banking/accounts/overview?schema=src")
    assert resp.status_code == 200
    cols = resp.json()["columns_summary"]
    assert cols
    for col in cols:
        assert "quality_grade" not in col
        assert "dq" in col
    currency = next(c for c in cols if c["name"] == "currency")
    _assert_scored_badge(currency["dq"])
    # Compact badge on lists — no full breakdown.
    assert "components" not in currency["dq"]


def test_list_tables_uses_dq_badge(client: TestClient):
    resp = client.get("/element/banking/tables")
    assert resp.status_code == 200
    tables = resp.json()
    accounts = next(t for t in tables if t["table_name"] == "accounts")
    for col in accounts["columns"]:
        assert "quality_grade" not in col
        assert "dq" in col


def test_element_dq_line_items_carry_evidence_note_through_the_api(client: TestClient):
    """U2d-fix — the API seam the three green suites never crossed.

    The scorer emits a per-line-item ``evidence_note`` and the frontend renders
    one from mock data, but neither test served a line-item through
    ``get_element`` → the store → the badge view. This asserts the plain-language
    note survives that round-trip on every scored line-item.
    """
    resp = client.get("/element/banking/accounts/currency?schema=src")
    assert resp.status_code == 200
    components = resp.json()["dq"]["components"]
    assert components

    seen_labels = set()
    for comp in components:
        for li in comp["line_items"]:
            note = li.get("evidence_note")
            assert note and note.strip(), (
                f"{comp['name']}/{li['label']} reached the API with no evidence_note"
            )
            seen_labels.add(li["label"])

    # Representative line-items from the closing brief must be present and noted.
    assert "Completeness" in seen_labels
    assert "Business Name" in seen_labels


# ── Polish Batch Task 6 — field-level re-evaluate (force re-score) ──────────

def test_dq_refresh_endpoint_forces_a_fresh_score(client: TestClient):
    # First view populates via GET (score-on-first-view path).
    first = client.get("/element/banking/accounts/currency/dq?schema=src").json()
    _assert_scored_badge(first)

    # POST refresh always re-scores (bypasses the cached/heal path) and returns
    # the same full breakdown shape the GET endpoint does.
    resp = client.post("/element/banking/accounts/currency/dq/refresh?schema=src")
    assert resp.status_code == 200
    refreshed = resp.json()
    _assert_scored_badge(refreshed)
    assert "components" in refreshed
    # Nothing about the underlying signals changed, so the score is stable.
    assert refreshed["dq_score"] == first["dq_score"]


def test_dq_refresh_endpoint_unknown_column_404(client: TestClient):
    resp = client.post("/element/banking/accounts/not_a_column/dq/refresh?schema=src")
    assert resp.status_code == 404

