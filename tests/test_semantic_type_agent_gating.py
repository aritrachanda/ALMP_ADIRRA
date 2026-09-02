from __future__ import annotations

import sys

from core.semantic_resolver import SemanticResolver
from core.semantic_type_store import SemanticTypeStore
from tests._pg_semantic_type_isolation import sandbox_semantic_type_tests

_sandbox_db, _sandbox_wipe = sandbox_semantic_type_tests()


def test_include_ai_false_does_not_import_agent(tmp_path):
    sys.modules.pop("agents.semantic_type_agent", None)
    resolver = SemanticResolver(store=SemanticTypeStore(tmp_path / "semantic_types.yaml"))

    result = resolver.resolve_table(
        source="banking",
        schema="src",
        table={
            "schema_name": "src",
            "table_name": "misc",
            "row_count": 3,
            "primary_key": [],
            "columns": [
                {"name": "value", "data_type": "DOUBLE", "row_count": 3, "distinct_count": 3, "sample_values": [1.2, 3.4, 5.6]},
            ],
        },
        include_ai=False,
    )

    assert result["columns"][0]["type_id"] == "unresolved"
    assert "agents.semantic_type_agent" not in sys.modules


def test_include_ai_true_failure_is_non_fatal(tmp_path, monkeypatch):
    from agents import semantic_type_agent

    def fail_residuals(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(semantic_type_agent, "resolve_residual_columns", fail_residuals)
    # Explicit empty overlay — isolates this test from core.semantic_resolver's shared,
    # process-wide learned-pattern cache (an order-dependent flake source; see tech-debt).
    resolver = SemanticResolver(store=SemanticTypeStore(tmp_path / "semantic_types.yaml"))

    result = resolver.resolve_table(
        source="banking",
        schema="src",
        table={
            "schema_name": "src",
            "table_name": "misc",
            "row_count": 3,
            "primary_key": [],
            "columns": [
                {"name": "value", "data_type": "DOUBLE", "row_count": 3, "distinct_count": 3, "sample_values": [1.2, 3.4, 5.6]},
            ],
        },
        include_ai=True,
    )

    assert result["columns"][0]["type_id"] == "unresolved"


def test_governance_context_is_passed_to_llm_residual_payload(tmp_path, monkeypatch):
    """Phase B: the provenance-tagged trio (governance_context) reaches the LLM
    residual payload for residual columns."""
    from agents import semantic_type_agent

    captured: dict = {}

    def capture_residuals(**kwargs):
        captured["residual_columns"] = kwargs.get("residual_columns")
        return []

    monkeypatch.setattr(semantic_type_agent, "resolve_residual_columns", capture_residuals)
    resolver = SemanticResolver(store=SemanticTypeStore(tmp_path / "semantic_types.yaml"))

    resolver.resolve_table(
        source="banking",
        schema="src",
        table={
            "schema_name": "src",
            "table_name": "misc",
            "row_count": 3,
            "primary_key": [],
            "columns": [
                {"name": "value", "data_type": "DOUBLE", "row_count": 3, "distinct_count": 3, "sample_values": [1.2, 3.4, 5.6]},
            ],
        },
        include_ai=True,
        governance_context={
            "value": {
                "definition": {"text": "the monetary value", "provenance": "human"},
                "business_name": {"text": "Value", "provenance": "human"},
            }
        },
    )

    residuals = captured.get("residual_columns") or []
    assert residuals, "expected a residual column to be sent to the LLM"
    gctx = residuals[0].get("governance_context")
    assert gctx and gctx["definition"]["provenance"] == "human"
    assert gctx["definition"]["text"] == "the monetary value"


def test_ai_format_tiebreak_updates_format_only(tmp_path, monkeypatch):
    from agents import semantic_type_agent

    def propose_format(**kwargs):
        residual = kwargs["residual_columns"][0]
        return [{
            "key": residual["key"],
            "type_id": "unresolved",
            "confidence": 0.7,
            "rationale": "Sibling dates use DDMMYYYY",
            "evidence_refs": ["sibling booking_date"],
            "format": "DDMMYYYY",
            "format_rationale": "Sibling dates use DDMMYYYY",
        }]

    monkeypatch.setattr(semantic_type_agent, "resolve_residual_columns", propose_format)
    resolver = SemanticResolver(store=SemanticTypeStore(tmp_path / "semantic_types.yaml"))

    result = resolver.resolve_table(
        source="banking",
        schema="src",
        table={
            "schema_name": "src",
            "table_name": "payments",
            "row_count": 2,
            "primary_key": [],
            "columns": [
                {"name": "datetime", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2, "sample_values": ["05112021", "06112021"]},
            ],
        },
        include_ai=True,
    )

    record = result["columns"][0]
    assert record["type_id"] == "date"
    assert record["format"] == "DDMMYYYY"
    assert record["format_source"] == "ai"
    assert not record.get("accepted_at")
