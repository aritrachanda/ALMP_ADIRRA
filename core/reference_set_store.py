"""Reference-set store for governed shared reference sets (Phase 3; Postgres-only since
Slice F of the governance YAML->Postgres migration).

A reference set is a reusable code list a source field can bind to. Sets live in the
``reference_set``/``reference_set_entry`` tables (see ``core.reference_set_repo``) — read-only
through this class; only the column-to-set BINDING (``core.element_state.ElementStateStore``)
has a real write path. The legacy ``governance/reference_sets.yaml`` hand-authored file was
retired once ``refset_backend`` had been live on Postgres and stable; it is archived, not
deleted (see ``docs/governance-postgres-migration.md``).

Set schema::

    id: str              # stable snake_case identifier (binding target)
    name: str
    kind: "standard" | "local"
    standard_ref: str | None
    status: str          # approved | candidate | under_review
    entries: list of {code, value, meaning, status, [aliases, effective_from, effective_to]}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ReferenceSetStore:
    def __init__(self, path: Path | None = None) -> None:
        """*path* is accepted (and ignored) for call-site compatibility with the pre-Postgres
        signature — every caller still passes it."""
        self._repo = None

    def _repository(self):
        if self._repo is None:
            from core.reference_set_repo import ReferenceSetRepo
            self._repo = ReferenceSetRepo()
        return self._repo

    def list(self) -> list[dict[str, Any]]:
        """Return all sets sorted by name."""
        return self._repository().list()

    def get(self, set_id: str) -> dict[str, Any] | None:
        """Return one set by id, or ``None`` if unknown."""
        return self._repository().get(set_id)

    def meanings(self, set_id: str) -> dict[str, str]:
        """Return ``{code: meaning}`` for a set's entries, or ``{}`` if unknown."""
        return self._repository().meanings(set_id)

    def values(self, set_id: str) -> dict[str, str]:
        """Return ``{code: value}`` (the code's expanded/full-word form) for a
        set's entries, or ``{}`` if unknown."""
        return self._repository().values(set_id)

