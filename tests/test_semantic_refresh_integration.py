"""Integration test for the semantic-type resolve-refresh path.

U0 Task 8: repairs a pre-existing broken test that imported a
``_rerun_semantic_resolution`` helper from ``api.routes.discovery`` which no
longer exists anywhere in the codebase (confirmed via repo-wide search).

The current production refresh entry point is
``core.semantic_resolver.SemanticResolver.resolve_table()`` — both real API
callers delegate to it directly:
  - ``api/semantic_types.py``'s ``POST /{source}/{table}/resolve`` route
    (``SemanticResolver(store=store, config=ResolverConfig.from_project(project)).resolve_table(...)``)
  - ``api/routes/element.py``'s ``_resolve_table_once()`` helper (used by the
    element/overview routes; fingerprinted, skips already-resolved columns)

This test exercises ``resolve_table`` directly at equivalent coverage to the
two callers above, matching the conventions already used in
tests/test_semantic_resolver.py.
"""
from __future__ import annotations

from core.semantic_resolver import ResolverConfig, SemanticResolver
from core.semantic_type_store import SemanticTypeStore
from tests._pg_semantic_type_isolation import sandbox_semantic_type_tests

_sandbox_db, _sandbox_wipe = sandbox_semantic_type_tests()


def _resolver(store: SemanticTypeStore) -> SemanticResolver:
    return SemanticResolver(store=store, config=ResolverConfig.from_project({}))


def test_refresh_reruns_resolution_and_updates_fingerprint(tmp_path):
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    profile = {
        "schema_name": "src",
        "table_name": "accounts",
        "row_count": 2,
        "primary_key": [],
        "columns": [
            {"name": "currency", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2, "sample_values": ["EUR", "USD"]}
        ],
    }

    result = _resolver(store).resolve_table(source="banking", schema="src", table=profile, include_ai=False, persist=True)
    record = store.get("banking", "src", "accounts", "currency")

    assert result["columns"][0]["type_id"] == "currency_code"
    assert record is not None
    assert record["fingerprint"]


def test_refresh_contradicting_accepted_type_preserves_record_and_emits_finding(tmp_path):
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    store.set_proposed(
        source="banking",
        schema="src",
        table="accounts",
        column="iban",
        type_id="iban",
        domain_role="identifier",
        confidence=0.98,
    )
    store.accept("banking", "src", "accounts", "iban", accepted_by="tester")

    profile = {
        "schema_name": "src",
        "table_name": "accounts",
        "row_count": 2,
        "primary_key": [],
        "columns": [
            {"name": "iban", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2, "sample_values": ["GB82WEST12345698765433", "DE89370400440532013001"]}
        ],
    }

    result = _resolver(store).resolve_table(source="banking", schema="src", table=profile, include_ai=False, persist=True)
    record = store.get("banking", "src", "accounts", "iban")

    assert record is not None
    assert record["accepted_at"]
    assert record["type_id"] == "iban"
    assert record["latest_proposal"]["type_value_conflict"] is True
    assert result["findings"]
    assert result["findings"][0]["category"] == "validity"

