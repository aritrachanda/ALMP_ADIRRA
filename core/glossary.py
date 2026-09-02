"""
Business glossary service — load/save/mutate glossary terms.

Streamlit-free on purpose: this module must be importable from any Python
context (CLI, tests, future Django views) so the UI is replaceable.

YAML shape (see openspec/changes/add-chat-and-glossary-ui/design.md, D3):

    version: 1
    categories:
      - name: Financial
        subcategories:
          - name: Banking
            terms:
              - title: Accounts payable turnover
                business_description: ...
                detailed_description: ...
                related_objects: [Object A, Object B]
      - name: Operational
        terms:
          - title: Member
            ...
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator, Optional

import yaml

# Repo-root-relative path to the glossary file.
_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = _ROOT / "glossary" / "glossary.yaml"


@dataclass
class Term:
    title: str
    business_description: str = ""
    detailed_description: str = ""
    regulatory_context: str = ""
    related_objects: list[str] = field(default_factory=list)


@dataclass
class TermLocation:
    """Where a term lives in the hierarchy."""
    category: str
    subcategory: Optional[str]   # None when the term hangs directly off a category
    term: Term


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_glossary(path: Path | None = None) -> dict:
    """Return the raw glossary dict. Returns an empty skeleton if the file is missing.

    Backend-aware: when ``database.glossary_backend`` is ``'postgres'`` the flat
    ``terms`` list is served from the relational store (so consumers like the chat
    agent don't read a stale ``glossary.yaml`` after the cutover). A custom ``path``
    always reads that file verbatim (used by importers/tests)."""
    if path is None:
        try:
            from core.glossary_db.read_api import _use_pg, glossary_terms
            if _use_pg():
                return {"version": 1, "categories": [], "terms": glossary_terms()}
        except Exception:
            pass
    p = path or GLOSSARY_PATH
    if not p.exists():
        return {"version": 1, "categories": []}
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("version", 1)
    data.setdefault("categories", [])
    return data


def save_glossary(data: dict, path: Path | None = None) -> None:
    """Persist the whole glossary to YAML."""
    p = path or GLOSSARY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def iter_terms(data: dict) -> Iterator[TermLocation]:
    """Yield every term in the glossary together with its location."""
    for cat in data.get("categories", []):
        cat_name = cat.get("name", "")
        if cat.get("subcategories"):
            for sub in cat["subcategories"]:
                sub_name = sub.get("name", "")
                for t in sub.get("terms", []) or []:
                    yield TermLocation(cat_name, sub_name, _term_from_dict(t))
        for t in cat.get("terms", []) or []:
            yield TermLocation(cat_name, None, _term_from_dict(t))


def find_term(
    data: dict,
    category: str,
    subcategory: Optional[str],
    title: str,
) -> Optional[TermLocation]:
    """Return the matching TermLocation or None."""
    for loc in iter_terms(data):
        if (
            loc.category == category
            and (loc.subcategory or None) == (subcategory or None)
            and loc.term.title == title
        ):
            return loc
    return None


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def upsert_term(
    data: dict,
    category: str,
    subcategory: Optional[str],
    term: Term,
    *,
    original_title: Optional[str] = None,
) -> None:
    """Insert or update a term in place inside `data`.

    `original_title` is used when renaming an existing term (so we know which
    one to replace). If omitted, the term is matched by `term.title`.
    """
    cat = _ensure_category(data, category)
    bucket = _ensure_term_bucket(cat, subcategory)
    match_title = original_title if original_title is not None else term.title
    for i, existing in enumerate(bucket):
        if existing.get("title") == match_title:
            bucket[i] = _term_to_dict(term)
            return
    bucket.append(_term_to_dict(term))


def delete_term(
    data: dict,
    category: str,
    subcategory: Optional[str],
    title: str,
) -> bool:
    """Remove a term. Returns True if deleted."""
    for cat in data.get("categories", []):
        if cat.get("name") != category:
            continue
        if subcategory:
            for sub in cat.get("subcategories", []) or []:
                if sub.get("name") == subcategory:
                    return _remove_from_bucket(sub.setdefault("terms", []), title)
        else:
            return _remove_from_bucket(cat.setdefault("terms", []), title)
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _term_from_dict(d: dict) -> Term:
    return Term(
        title=d.get("title", ""),
        business_description=d.get("business_description", "") or "",
        detailed_description=d.get("detailed_description", "") or "",
        regulatory_context=d.get("regulatory_context", "") or "",
        related_objects=list(d.get("related_objects") or []),
    )


def _term_to_dict(t: Term) -> dict:
    out = asdict(t)
    # Drop keys that are empty to keep the YAML tidy.
    if not out["related_objects"]:
        out["related_objects"] = []
    return out


def _ensure_category(data: dict, name: str) -> dict:
    for cat in data.setdefault("categories", []):
        if cat.get("name") == name:
            return cat
    cat = {"name": name}
    data["categories"].append(cat)
    return cat


def _ensure_term_bucket(cat: dict, subcategory: Optional[str]) -> list[dict]:
    if subcategory:
        for sub in cat.setdefault("subcategories", []):
            if sub.get("name") == subcategory:
                return sub.setdefault("terms", [])
        sub = {"name": subcategory, "terms": []}
        cat.setdefault("subcategories", []).append(sub)
        return sub["terms"]
    return cat.setdefault("terms", [])


def _remove_from_bucket(bucket: list[dict], title: str) -> bool:
    for i, item in enumerate(bucket):
        if item.get("title") == title:
            del bucket[i]
            return True
    return False
