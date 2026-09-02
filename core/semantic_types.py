"""Governed semantic-type vocabulary loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from core.type_validators import known_validators

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VOCABULARY_PATH = _ROOT / "governance" / "semantic_types.yaml"
_RESERVED_UNRESOLVED = "unresolved"

_ALLOWED_CATEGORIES = {
    "natural_id", "surrogate_id", "monetary", "quantity", "rate", "temporal", "code",
    "name", "address", "text", "technical",
    # Legacy (kept for backward compat during migration)
    "identifier", "textual", "classification",
}
_ALLOWED_PRIMITIVES = {"string", "integer", "decimal", "date", "boolean"}


@dataclass(frozen=True)
class SemanticTypeEntry:
    id: str
    label: str
    category: str
    primitive: tuple[str, ...]
    detectors: dict[str, Any]
    expectations: tuple[str, ...]
    regulatory: dict[str, Any]
    confirmation_kind: str          # validator | distribution | shape | none (regex is not a value)
    scope_source: str               # global_standard | national_standard | distribution | default
    pii: dict[str, Any]             # {is_pii: bool, category: str|None}

    @property
    def name_tokens(self) -> tuple[str, ...]:
        tokens = self.detectors.get("name_tokens") or []
        return tuple(str(token).lower() for token in tokens if str(token).strip())

    @property
    def value_regex(self) -> str | None:
        value = self.detectors.get("value_regex")
        return str(value) if value else None

    @property
    def validator(self) -> str | None:
        value = self.detectors.get("validator")
        return str(value) if value else None


class SemanticVocabulary:
    def __init__(self, entries: Iterable[SemanticTypeEntry]) -> None:
        by_id: dict[str, SemanticTypeEntry] = {}
        for entry in entries:
            if entry.id in by_id:
                raise ValueError(f"Duplicate semantic type id: {entry.id}")
            by_id[entry.id] = entry
        self._entries = by_id

    @property
    def entries(self) -> list[SemanticTypeEntry]:
        return list(self._entries.values())

    @property
    def ids(self) -> set[str]:
        return set(self._entries.keys())

    def get(self, type_id: str) -> SemanticTypeEntry | None:
        return self._entries.get(type_id)

    def is_assignable(self, type_id: str | None) -> bool:
        return type_id == _RESERVED_UNRESOLVED or bool(type_id and type_id in self._entries)

    def assignable_or_unresolved(self, type_id: str | None) -> str:
        return type_id if self.is_assignable(type_id) and type_id else _RESERVED_UNRESOLVED


def _normalise_entry(raw: dict[str, Any]) -> SemanticTypeEntry:
    if not isinstance(raw, dict):
        raise ValueError("Semantic type entry must be a mapping")
    type_id = str(raw.get("id") or "").strip()
    if not type_id:
        raise ValueError("Semantic type entry missing id")
    if type_id == _RESERVED_UNRESOLVED:
        raise ValueError("'unresolved' is reserved and cannot appear in the vocabulary")

    label = str(raw.get("label") or type_id).strip()
    category = str(raw.get("category") or "").strip()
    if category not in _ALLOWED_CATEGORIES:
        raise ValueError(f"Semantic type {type_id!r} has invalid category {category!r}")

    primitives = tuple(str(item).strip() for item in (raw.get("primitive") or []) if str(item).strip())
    if not primitives or any(item not in _ALLOWED_PRIMITIVES for item in primitives):
        raise ValueError(f"Semantic type {type_id!r} has invalid primitive list")

    detectors = raw.get("detectors") or {}
    if not isinstance(detectors, dict):
        raise ValueError(f"Semantic type {type_id!r} detectors must be a mapping")
    validator = detectors.get("validator")
    if validator and str(validator) not in known_validators():
        raise ValueError(f"Semantic type {type_id!r} references unknown validator {validator!r}")

    expectations = tuple(str(item) for item in (raw.get("expectations") or []))
    regulatory = raw.get("regulatory") or {}
    if not isinstance(regulatory, dict):
        regulatory = {}
    confirmation_kind = str(raw.get("confirmation_kind") or "none").strip()
    scope_source = str(raw.get("scope_source") or "default").strip()
    pii_raw = raw.get("pii") or {}
    pii = {"is_pii": bool(pii_raw.get("is_pii", False)), "category": pii_raw.get("category")}

    return SemanticTypeEntry(
        id=type_id,
        label=label,
        category=category,
        primitive=primitives,
        detectors=detectors,
        expectations=expectations,
        regulatory=regulatory,
        confirmation_kind=confirmation_kind,
        scope_source=scope_source,
        pii=pii,
    )


def load_semantic_vocabulary(path: Path | None = None) -> SemanticVocabulary:
    vocabulary_path = path or _DEFAULT_VOCABULARY_PATH
    with vocabulary_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    if not isinstance(raw, list):
        raise ValueError("Semantic vocabulary must be a list of entries")
    return SemanticVocabulary(_normalise_entry(entry) for entry in raw)
