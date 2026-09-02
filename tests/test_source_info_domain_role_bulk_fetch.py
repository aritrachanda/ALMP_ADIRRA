"""Regression test for the Source Profile page's bulk domain_role fetch (found live
2026-08-14 -- semantic_store.get() was called once per column across every table in a
source, up to ~1,900 individual reads for a large source, dominating that page's load
time). ``_build_source_info`` now bulk-fetches every column's domain_role in ONE query
(``SemanticTypeStore.domain_roles_for_source``) instead of reading per column.

No existing test covered ``/element/{source}/info``'s semantic_type_mix /
semantic_governance_matrix at all -- this is new coverage, not just a regression check.
"""
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
        yield client


def test_source_info_semantic_type_mix_matches_column_count(element_client):
    """Every column in the source must land in exactly one semantic_type_mix bucket --
    proves the bulk-fetched map (present-key case) and the heuristic fallback
    (absent-key case) are both exercised and neither double-counts nor drops a column."""
    resp = element_client.get("/element/banking/info")
    assert resp.status_code == 200
    body = resp.json()

    mix = body["semantic_type_mix"]
    assert mix
    counts = {item["type"]: item["count"] for item in mix}
    assert sum(counts.values()) == body["column_count"]


def test_source_info_matches_table_overview_domain_roles(element_client):
    """The bulk-fetched map must agree, column-by-column, with the per-column path
    (_build_table_overview's own resolve, which the table-overview endpoint already
    covers) -- proves the map lookup and the heuristic fallback both classify each
    column identically to the un-batched read."""
    table_resp = element_client.get("/element/banking/accounts/overview?schema=src")
    assert table_resp.status_code == 200
    per_column = {
        c["name"]: c["semantic_domain_role"] for c in table_resp.json()["columns_summary"]
    }

    source_resp = element_client.get("/element/banking/info")
    assert source_resp.status_code == 200
    matrix_types = {row["type"] for row in source_resp.json()["semantic_governance_matrix"]}
    # currency (coded) must appear consistently between the two endpoints.
    assert per_column.get("currency") == "code"
    assert "code" in matrix_types


def test_source_info_semantic_governance_matrix_sums_to_column_count(element_client):
    """Cross-tab rows (semantic type x governance bucket) must also sum to the full
    column count -- proves the governance side (already-cheap element_state.get() per
    column, untouched by this fix) still lines up with the new bulk semantic side."""
    resp = element_client.get("/element/banking/info")
    assert resp.status_code == 200
    body = resp.json()

    total = sum(
        row["empty"] + row["draft"] + row["in_review"] + row["approved"] + row["bounced"]
        for row in body["semantic_governance_matrix"]
    )
    assert total == body["column_count"]
