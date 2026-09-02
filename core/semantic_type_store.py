"""Postgres-backed store for per-column semantic-type assignments (Postgres-only since
Slice F of the governance YAML->Postgres migration).

The legacy ``governance/semantic_type_assignments.yaml`` file (and the load-time old-vocabulary
type-id migration it once needed) was retired once ``semantic_backend`` had been live on
Postgres and stable; the file is archived, not deleted (see
``docs/governance-postgres-migration.md``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

SemanticTypeSource = Literal["rule", "ai"]

_DEFAULT_TYPE_ID = "unresolved"


class _NULL_BATCH:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SemanticTypeStore:
    def __init__(self, path: Path | None = None) -> None:
        """*path* is accepted (and ignored) for call-site compatibility with the pre-Postgres
        signature — every caller still passes it."""
        self._repo_instance = None

    def _repo(self):
        if self._repo_instance is None:
            from core.semantic_type_repo import SemanticTypeRepo
            self._repo_instance = SemanticTypeRepo()
        return self._repo_instance

    def batch(self):
        """No-op context manager — each write is already a small, isolated upsert, so there
        is no whole-file cost to coalesce. Kept so callers written for the old YAML-batching
        behaviour need no changes."""
        return _NULL_BATCH()

    @staticmethod
    def key(source: str, schema: str | None, table: str, column: str) -> str:
        return f"{source}|{schema or ''}|{table}|{column}"

    @staticmethod
    def split_key(key: str) -> dict[str, str]:
        parts = key.split("|", 3)
        if len(parts) != 4:
            return {"source": "", "schema": "", "table": "", "column": key}
        source, schema, table, column = parts
        return {"source": source, "schema": schema, "table": table, "column": column}

    @staticmethod
    def default_record(
        *,
        source: str,
        schema: str | None,
        table: str,
        column: str,
    ) -> dict[str, Any]:
        key = SemanticTypeStore.key(source, schema, table, column)
        return {
            "key": key,
            "type_id": _DEFAULT_TYPE_ID,
            "domain_role": "unresolved",
            "confidence": 0.0,
            "source": "rule",
            "candidates": [],
            "evidence": [],
            "type_value_conflict": False,
            "type_datatype_difference": False,
            "format": None,
            "format_source": None,
            "format_rationale": None,
            "scope": None,
            "entity": None,
            "pii": False,
            "pii_category": None,
            "resolver_version": "1",
            "resolved_at": None,
            "accepted_by": None,
            "accepted_by_role": None,
            "accepted_at": None,
            "fingerprint": None,
            "system_deduced_type": None,
        }

    def get(self, source: str, schema: str | None, table: str, column: str) -> dict[str, Any] | None:
        return self._repo().get(source, schema, table, column)

    def get_or_default(self, source: str, schema: str | None, table: str, column: str) -> dict[str, Any]:
        return self._repo().get_or_default(source, schema, table, column)

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        return self._repo().get_by_key(key)

    def domain_roles_for_source(self, source: str) -> dict[str, str]:
        return self._repo().domain_roles_for_source(source)

    def semantic_states_for_source(self, source: str) -> dict[str, int]:
        return self._repo().semantic_states_for_source(source)

    def set_record(self, record: dict[str, Any], *, preserve_disposed: bool = True) -> dict[str, Any]:
        return self._repo().set_record(record, preserve_disposed=preserve_disposed)

    def set_proposed(
        self,
        *,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        type_id: str,
        domain_role: str,
        confidence: float,
        candidates: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        resolver_source: SemanticTypeSource = "rule",
        type_value_conflict: bool = False,
        type_datatype_difference: bool = False,
        format: str | None = None,
        format_source: str | None = None,
        format_rationale: str | None = None,
        scope: str | None = None,
        entity: str | None = None,
        pii: bool = False,
        pii_category: str | None = None,
        fingerprint: str | None = None,
        resolver_version: str = "1",
    ) -> dict[str, Any]:
        return self._repo().set_proposed(
            source=source, schema=schema, table=table, column=column, type_id=type_id,
            domain_role=domain_role, confidence=confidence, candidates=candidates,
            evidence=evidence, resolver_source=resolver_source,
            type_value_conflict=type_value_conflict,
            type_datatype_difference=type_datatype_difference, format=format,
            format_source=format_source, format_rationale=format_rationale, scope=scope,
            entity=entity, pii=pii, pii_category=pii_category, fingerprint=fingerprint,
            resolver_version=resolver_version,
        )

    def accept(
        self,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        *,
        accepted_by: str | None = None,
        accepted_by_role: str | None = None,
        type_id: str | None = None,
        domain_role: str | None = None,
    ) -> dict[str, Any]:
        return self._repo().accept(
            source, schema, table, column,
            accepted_by=accepted_by, accepted_by_role=accepted_by_role,
            type_id=type_id, domain_role=domain_role,
        )

    def record_submission(
        self,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        *,
        deduced_type_id: str,
        deduced_domain_role: str | None = None,
        deduced_confidence: float | None = None,
        deduced_tier: int | None = None,
        deduced_resolver_version: str | None = None,
        submitted_by: str | None = None,
    ) -> dict[str, Any]:
        """Open a new Interpretation Set submission history window (B1 D1)."""
        return self._repo().record_submission(
            source, schema, table, column,
            deduced_type_id=deduced_type_id, deduced_domain_role=deduced_domain_role,
            deduced_confidence=deduced_confidence, deduced_tier=deduced_tier,
            deduced_resolver_version=deduced_resolver_version, submitted_by=submitted_by,
        )

    def find_in_source(self, source: str) -> list[dict[str, Any]]:
        return self._repo().find_in_source(source)

    def find_table(self, source: str, schema: str | None, table: str) -> list[dict[str, Any]]:
        return self._repo().find_table(source, schema, table)

