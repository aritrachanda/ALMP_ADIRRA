"""Document metadata store for source documents (data dictionaries, mapping specs, etc.).

Documents are indexed in a YAML file; file bytes are stored on disk under documents_root.
Thread-safe writes; one YAML index shared across all sources.

Schema (per record):
  id: UUID string
  source: source system name
  name: display name
  doc_type: Data Dictionary | Mapping Spec | System Spec | Quality Rules | Other
  description: free text
  owner: owner / team name
  scope: System-level | Source-level | Table-level | Column-level
  file_name: original filename or null (metadata-only record)
  file_path: path relative to documents_root, or null
  file_size_kb: float or null
  uploaded_at: ISO timestamp
  ai_permissions: {definitions: bool, mapping: bool, quality: bool}
  synopsis: AI-generated synopsis text or null
  synopsis_generated_at: ISO timestamp or null
  synopsis_is_ai: bool
"""
from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

_RECORDS_KEY = "documents"


class DocumentStore:
    """Thread-safe YAML-backed store for document metadata."""

    def __init__(self, index_path: Path, documents_root: Path) -> None:
        self._path = index_path
        self._root = documents_root
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with self._path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            raw.setdefault(_RECORDS_KEY, {})
            return raw
        return {_RECORDS_KEY: {}}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(self._data, fh, default_flow_style=False,
                          sort_keys=False, allow_unicode=True)

    # ── File path helpers ──────────────────────────────────────────────────

    def file_path(self, source: str, doc_id: str, filename: str) -> Path:
        """Absolute path where the document file should be stored."""
        return self._root / source / doc_id / filename

    # ── CRUD ──────────────────────────────────────────────────────────────

    def list_source(self, source: str) -> list[dict[str, Any]]:
        """Return all document records for a given source, newest first."""
        docs = [
            deepcopy(v)
            for v in self._data[_RECORDS_KEY].values()
            if v.get("source") == source
        ]
        docs.sort(key=lambda d: d.get("uploaded_at") or "", reverse=True)
        return docs

    def get(self, doc_id: str) -> dict[str, Any] | None:
        record = self._data[_RECORDS_KEY].get(doc_id)
        return deepcopy(record) if record else None

    def add(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Persist a new document record. The doc dict must include an 'id' field."""
        doc_id = str(doc["id"])
        with self._lock:
            self._data[_RECORDS_KEY][doc_id] = doc
            self._save()
        return deepcopy(doc)

    def delete(self, doc_id: str) -> bool:
        """Remove a document record. Returns True if it existed."""
        with self._lock:
            if doc_id in self._data[_RECORDS_KEY]:
                del self._data[_RECORDS_KEY][doc_id]
                self._save()
                return True
        return False

    def set_synopsis(
        self, doc_id: str, synopsis: str, *, is_ai: bool = True
    ) -> dict[str, Any] | None:
        """Update the synopsis fields on an existing record."""
        with self._lock:
            record = self._data[_RECORDS_KEY].get(doc_id)
            if record is None:
                return None
            record["synopsis"] = synopsis
            record["synopsis_generated_at"] = datetime.now().isoformat()
            record["synopsis_is_ai"] = is_ai
            self._save()
            return deepcopy(record)

    @staticmethod
    def default_record(
        *,
        doc_id: str,
        source: str,
        name: str,
        doc_type: str,
        description: str = "",
        owner: str = "",
        scope: str = "Source-level",
        file_name: str | None = None,
        file_path_rel: str | None = None,
        file_size_kb: float | None = None,
        ai_permissions: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": doc_id,
            "source": source,
            "name": name,
            "doc_type": doc_type,
            "description": description,
            "owner": owner,
            "scope": scope,
            "file_name": file_name,
            "file_path": file_path_rel,
            "file_size_kb": file_size_kb,
            "uploaded_at": datetime.now().isoformat(),
            "ai_permissions": ai_permissions or {"definitions": True, "mapping": True, "quality": False},
            "synopsis": None,
            "synopsis_generated_at": None,
            "synopsis_is_ai": False,
        }
