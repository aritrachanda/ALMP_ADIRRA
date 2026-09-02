"""
glossary_agent.py  —  Business Glossary agent for AI-TIMO.

Responsibilities
----------------
1. CRUD operations on glossary/glossary.yaml (load, save, add, update, delete).
2. Full-text search across title, synonyms, business_description, detailed_description
   and tags — used both by the UI and by the future home-page chat agent.
3. Cross-reference resolution: given a catalog object reference string
   ("source|banking|src.counterparties.annual_turnover"), return all terms that
   mention it in their related_objects list.
4. (Future) AI-assisted definition drafting — interface is already defined here;
   the LLM call is a no-op stub until a provider key is configured.

Usage (standalone)
------------------
    python agents/glossary_agent.py --search "credit"
    python agents/glossary_agent.py --term credit_quality_step

Chat-agent integration
----------------------
Call ``GlossaryAgent.answer(user_text)`` from a home-page chat handler.  It
returns a list of matching GlossaryTerm objects (possibly empty).  The caller
is responsible for rendering them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "core"))

from annotations import get_table_annotations, load_annotations
from yaml_cache import load_yaml_cached

GLOSSARY_FILE = _ROOT / "glossary" / "glossary.yaml"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GlossaryTerm:
    id: str
    domain: str
    category: str
    title: str
    business_description: str = ""
    detailed_description: str = ""
    synonyms: list[str] = field(default_factory=list)
    related_objects: list[str] = field(default_factory=list)
    steward: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = "draft"
    CRR_context: str = ""
    DPM_context: str = ""
    ai_generated_fields: list[str] = field(default_factory=list)
    last_updated: str | None = None
    last_reviewed: str | None = None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def _legacy_ai_generated_fields(d: dict) -> list[str]:
        fields: list[str] = []
        if d.get("related_objects"):
            if d.get("title"):
                fields.append("title")
            if d.get("domain"):
                fields.append("domain")
            if d.get("category"):
                fields.append("category")
            if d.get("business_description"):
                fields.append("business_description")
            if d.get("detailed_description"):
                fields.append("detailed_description")
            if d.get("synonyms"):
                fields.append("synonyms")
            if d.get("tags"):
                fields.append("tags")
        return fields

    @classmethod
    def from_dict(cls, d: dict) -> "GlossaryTerm":
        ai_generated_fields = d.get("ai_generated_fields") or []
        if not ai_generated_fields:
            ai_generated_fields = cls._legacy_ai_generated_fields(d)
        return cls(
            id=d.get("id", ""),
            domain=d.get("domain", ""),
            category=d.get("category", ""),
            title=d.get("title", ""),
            business_description=d.get("business_description", ""),
            detailed_description=d.get("detailed_description", ""),
            synonyms=d.get("synonyms") or [],
            related_objects=d.get("related_objects") or [],
            steward=d.get("steward", ""),
            tags=d.get("tags") or [],
            status=d.get("status", "draft"),
            CRR_context=d.get("CRR_context", ""),
            DPM_context=d.get("DPM_context", ""),
            ai_generated_fields=ai_generated_fields,
            last_updated=d.get("last_updated"),
            last_reviewed=d.get("last_reviewed"),
        )

    def matches(self, query: str) -> bool:
        """Return True if *query* appears in any searchable text field (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return True
        haystack = " ".join([
            self.title,
            self.business_description,
            self.detailed_description,
            " ".join(self.synonyms),
            " ".join(self.tags),
            self.domain,
            self.category,
        ]).lower()
        # Support multi-word and partial matching
        return all(token in haystack for token in q.split())


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class GlossaryAgent:
    """Manages the business glossary and exposes search / CRUD APIs.

    Dual-backend: when ``database.glossary_backend`` (project.yaml) / the
    ``ADIRRA_GLOSSARY_BACKEND`` env var is ``'postgres'``, every method delegates to the
    v2 relational store (``core.glossary_db``); otherwise the legacy YAML store is used.
    The public interface (signatures + GlossaryTerm return types) is identical in both.
    Default is ``'yaml'`` so the running app is unchanged until Phase 3 migrates the data.
    """

    def __init__(self, glossary_file: Path = GLOSSARY_FILE):
        self._file = glossary_file
        self._terms: list[GlossaryTerm] = []
        if not self._use_pg():
            self._load()

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @staticmethod
    def _use_pg() -> bool:
        try:
            from core.glossary_db.db import backend
            return backend() == "postgres"
        except Exception:
            return False

    @contextmanager
    def _repo(self):
        """Yield a repository inside a committed session scope (Postgres backend)."""
        from core.glossary_db.db import session_scope
        from core.glossary_db.repository import GlossaryRepository
        with session_scope() as session:
            yield GlossaryRepository(session)

    # ------------------------------------------------------------------
    # Internal I/O
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file.exists():
            self._terms = []
            return
        with self._file.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        migrated = False
        terms: list[GlossaryTerm] = []
        for raw_term in data.get("terms", []):
            stored_ai_fields = raw_term.get("ai_generated_fields") or []
            term = GlossaryTerm.from_dict(raw_term)
            if term.ai_generated_fields != stored_ai_fields:
                migrated = True
            terms.append(term)
        # In-memory backfill only — do NOT silently re-write the file on load (that was a
        # surprising read-time mutation; defect fixed in Phase 2).
        self._terms = terms

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "terms": [t.to_dict() for t in self._terms],
        }
        with self._file.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all_terms(self) -> list[GlossaryTerm]:
        if self._use_pg():
            with self._repo() as repo:
                return [GlossaryTerm.from_dict(d) for d in repo.list_terms()]
        return list(self._terms)

    def get(self, term_id: str) -> Optional[GlossaryTerm]:
        if self._use_pg():
            with self._repo() as repo:
                d = repo.get_term(term_id)
                return GlossaryTerm.from_dict(d) if d else None
        for t in self._terms:
            if t.id == term_id:
                return t
        return None

    def search(self, query: str) -> list[GlossaryTerm]:
        """Return terms whose text fields contain all words in *query*."""
        if self._use_pg():
            with self._repo() as repo:
                return [GlossaryTerm.from_dict(d) for d in repo.search(query)]
        return [t for t in self._terms if t.matches(query)]

    def by_domain_category(self) -> dict[str, dict[str, list[GlossaryTerm]]]:
        """Return {domain: {category: [terms]}} structure for tree rendering."""
        if self._use_pg():
            with self._repo() as repo:
                tree_d = repo.by_domain_category()
            return {
                domain: {cat: [GlossaryTerm.from_dict(d) for d in terms] for cat, terms in cats.items()}
                for domain, cats in tree_d.items()
            }
        tree: dict[str, dict[str, list[GlossaryTerm]]] = {}
        for t in self._terms:
            tree.setdefault(t.domain, {}).setdefault(t.category, []).append(t)
        return tree

    def cross_references(self, catalog_ref: str) -> list[GlossaryTerm]:
        """Return all terms whose related_objects include *catalog_ref*."""
        if self._use_pg():
            with self._repo() as repo:
                return [GlossaryTerm.from_dict(d) for d in repo.cross_references(catalog_ref)]
        return [t for t in self._terms if catalog_ref in t.related_objects]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _is_approved(status: str | None) -> bool:
        return (status or "").strip().lower() == "approved"

    def _title_taken(self, title: str) -> bool:
        """Case-insensitive exact-title collision check across all existing terms."""
        normalized = title.strip().lower()
        if not normalized:
            return False
        if self._use_pg():
            with self._repo() as repo:
                return any((d.get("title") or "").strip().lower() == normalized for d in repo.list_terms())
        return any(t.title.strip().lower() == normalized for t in self._terms)

    def add(self, term: GlossaryTerm) -> GlossaryTerm:
        """Add a new term.  Generates an id if blank.  Raises ValueError on duplicate id
        or on a title that already exists (case-insensitive) — a glossary term is meant to be
        the one canonical definition linked from many catalog columns, not re-created per column."""
        if self._title_taken(term.title):
            raise ValueError(f"A term titled '{term.title.strip()}' already exists.")
        if not term.id:
            term.id = re.sub(r"[^a-z0-9]+", "_", term.title.lower()).strip("_")
            base = term.id
            counter = 2
            while self.get(term.id) is not None:
                term.id = f"{base}_{counter}"
                counter += 1
        elif self.get(term.id):
            raise ValueError(f"Term with id '{term.id}' already exists.")

        if self._is_approved(term.status) and not term.last_reviewed:
            term.last_reviewed = self._now_iso()

        if self._use_pg():
            with self._repo() as repo:
                return GlossaryTerm.from_dict(repo.insert_term(term.to_dict()))
        self._terms.append(term)
        self._save()
        return term

    def update(self, term: GlossaryTerm) -> GlossaryTerm:
        """Replace an existing term by id.  Raises KeyError if not found."""
        if self._use_pg():
            existing = self.get(term.id)
            if existing is None:
                raise KeyError(f"Term '{term.id}' not found.")
            if not self._is_approved(existing.status) and self._is_approved(term.status) and not term.last_reviewed:
                term.last_reviewed = self._now_iso()
            with self._repo() as repo:
                return GlossaryTerm.from_dict(repo.update_term(term.to_dict()))
        for i, t in enumerate(self._terms):
            if t.id == term.id:
                if not self._is_approved(t.status) and self._is_approved(term.status):
                    term.last_reviewed = self._now_iso()
                self._terms[i] = term
                self._save()
                return term
        raise KeyError(f"Term '{term.id}' not found.")

    def delete(self, term_id: str) -> None:
        """Remove a term by id.  Raises KeyError if not found."""
        if self._use_pg():
            with self._repo() as repo:
                repo.delete_term(term_id)
            return
        before = len(self._terms)
        self._terms = [t for t in self._terms if t.id != term_id]
        if len(self._terms) == before:
            raise KeyError(f"Term '{term_id}' not found.")
        self._save()

    # ------------------------------------------------------------------
    # Chat-agent integration
    # ------------------------------------------------------------------

    def answer(self, user_text: str) -> list[GlossaryTerm]:
        """
        Entry point called by the home-page chat handler.

        Given free-form user text, returns the most relevant glossary terms.
        Currently uses keyword matching.  When an LLM key is configured this
        method can be enhanced to use embedding similarity or a prompt chain.
        """
        results = self.search(user_text)
        # Fall back to title prefix matching if keyword search returns nothing
        if not results:
            q = user_text.strip().lower()
            results = [t for t in self.all_terms() if t.title.lower().startswith(q)]
        return results

    def _load_agent_config(self) -> dict:
        project_file = _ROOT / "project.yaml"
        with project_file.open(encoding="utf-8") as fh:
            project = yaml.safe_load(fh)
        return project.get("agent", {})

    def _load_project(self) -> dict:
        project_file = _ROOT / "project.yaml"
        with project_file.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    @staticmethod
    def _catalog_dir(project: dict, kind: str) -> Path:
        paths = project.get("paths", {})
        if kind == "target":
            return _ROOT / paths.get("target_catalogs", "targets")
        return _ROOT / paths.get("source_catalogs", "sources")

    @staticmethod
    def _mappings_dir() -> Path:
        return _ROOT / "mappings"

    @staticmethod
    def _normalize_lookup_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    def _term_lookup_candidates(self, term: GlossaryTerm) -> set[str]:
        candidates = {
            self._normalize_lookup_text(term.title),
            self._normalize_lookup_text(term.title.replace("_", " ")),
        }
        for synonym in term.synonyms:
            candidates.add(self._normalize_lookup_text(synonym))
            candidates.add(self._normalize_lookup_text(str(synonym).replace("_", " ")))
        return {candidate for candidate in candidates if candidate}

    @staticmethod
    def _parse_related_object(ref: str) -> dict | None:
        parts = [part.strip() for part in ref.split("|", 2)]
        if len(parts) != 3:
            return None
        object_path = [segment.strip() for segment in parts[2].split(".") if segment.strip()]
        if len(object_path) < 3:
            return None
        return {
            "kind": parts[0],
            "dataset": parts[1],
            "schema": object_path[0],
            "table": object_path[1],
            "column": ".".join(object_path[2:]),
            "ref": ref,
        }

    def _build_catalog_context(
        self,
        *,
        catalog: dict,
        dataset: str,
        kind: str,
        schema_name: str,
        table: dict,
        column: dict,
        table_annotations: dict,
        ref: str,
    ) -> dict:
        column_annotations = table_annotations.get("columns", {}).get(column.get("name", ""), {})
        column_keys = [
            "name",
            "description",
            "data_type",
            "row_count",
            "null_count",
            "null_pct",
            "distinct_count",
            "min_value",
            "max_value",
            "sample_values",
        ]
        table_keys = [
            "description",
            "row_count",
            "primary_key",
            "foreign_keys",
            "relations",
        ]

        column_catalog = {key: column.get(key) for key in column_keys}
        column_catalog["user_description"] = column_annotations.get("user_description") or ""
        column_catalog["mapping_instructions"] = column_annotations.get("mapping_instructions") or ""

        table_catalog = {key: table.get(key) for key in table_keys}
        table_catalog["user_description"] = table_annotations.get("user_description") or ""
        table_catalog["mapping_instructions"] = table_annotations.get("mapping_instructions") or ""

        table_columns = []
        for sibling in table.get("columns", []):
            sibling_annotations = table_annotations.get("columns", {}).get(sibling.get("name", ""), {})
            sibling_catalog = {key: sibling.get(key) for key in column_keys}
            sibling_catalog["user_description"] = sibling_annotations.get("user_description") or ""
            sibling_catalog["mapping_instructions"] = sibling_annotations.get("mapping_instructions") or ""
            table_columns.append(sibling_catalog)

        return {
            "ref": ref,
            "kind": kind,
            "dataset": dataset,
            "schema": schema_name,
            "table": table.get("table_name", table.get("name", "")),
            "column": column.get("name", ""),
            "catalog_generated_at": catalog.get("generated_at"),
            "schema_hash": catalog.get("schema_hash"),
            "column_catalog": column_catalog,
            "table_catalog": table_catalog,
            "table_columns": table_columns,
            "mapping_contexts": self._mapping_contexts(
                dataset=dataset,
                schema_name=schema_name,
                table_name=table.get("table_name", table.get("name", "")),
                column_name=column.get("name", ""),
            ),
        }

    def _mapping_contexts(self, *, dataset: str, schema_name: str, table_name: str, column_name: str) -> list[dict]:
        mappings_dir = self._mappings_dir()
        if not mappings_dir.exists():
            return []

        contexts: list[dict] = []
        for mapping_path in sorted(mappings_dir.glob("*.yaml")):
            mapping = load_yaml_cached(mapping_path)
            if mapping.get("source") != dataset:
                continue

            for table_mapping in mapping.get("tables", []):
                matched_columns = []
                for column_mapping in table_mapping.get("columns", []):
                    if (
                        (column_mapping.get("source_schema") or "") == schema_name
                        and (column_mapping.get("source_table") or "") == table_name
                        and (column_mapping.get("source_column") or "") == column_name
                    ):
                        matched_columns.append(
                            {
                                "target_schema": table_mapping.get("target_schema", ""),
                                "target_table": table_mapping.get("target_table", ""),
                                "target_framework": table_mapping.get("target_framework", ""),
                                "target_column": column_mapping.get("target_column", ""),
                                "confidence": column_mapping.get("confidence"),
                                "rationale": column_mapping.get("rationale") or "",
                                "transformation_type": column_mapping.get("transformation_type") or "",
                                "notes": column_mapping.get("notes") or "",
                                "status": column_mapping.get("status") or "",
                            }
                        )

                if matched_columns:
                    contexts.append(
                        {
                            "mapping_file": mapping_path.name,
                            "target": mapping.get("target", ""),
                            "agent": mapping.get("agent", ""),
                            "provider": mapping.get("provider", ""),
                            "model": mapping.get("model", ""),
                            "generated_at": mapping.get("generated_at"),
                            "status": mapping.get("status", ""),
                            "table_context": {
                                "target_schema": table_mapping.get("target_schema", ""),
                                "target_table": table_mapping.get("target_table", ""),
                                "target_framework": table_mapping.get("target_framework", ""),
                                "table_confidence": table_mapping.get("table_confidence"),
                                "table_rationale": table_mapping.get("table_rationale") or "",
                                "sql_query": table_mapping.get("sql_query") or "",
                            },
                            "column_mappings": matched_columns,
                        }
                    )

        return contexts

    def _related_catalog_contexts(self, related_objects: list[str]) -> list[dict]:
        project = self._load_project()
        catalog_cache: dict[tuple[str, str], tuple[dict, dict]] = {}
        contexts: list[dict] = []

        for ref in related_objects:
            parsed = self._parse_related_object(ref)
            if not parsed:
                continue

            cache_key = (parsed["kind"], parsed["dataset"])
            if cache_key not in catalog_cache:
                catalog_dir = self._catalog_dir(project, parsed["kind"])
                catalog_path = catalog_dir / f"{parsed['dataset']}.yaml"
                if not catalog_path.exists():
                    continue
                catalog_cache[cache_key] = (
                    load_yaml_cached(catalog_path),
                    load_annotations(parsed["dataset"], catalog_dir),
                )

            catalog, annotations = catalog_cache[cache_key]
            schema_match = next(
                (schema for schema in catalog.get("schemas", []) if schema.get("name", "") == parsed["schema"]),
                None,
            )
            if not schema_match and parsed["schema"].lower() == "src":
                schema_match = next(
                    (
                        schema
                        for schema in catalog.get("schemas", [])
                        if any(
                            table.get("table_name", table.get("name", "")) == parsed["table"]
                            for table in schema.get("tables", [])
                        )
                    ),
                    None,
                )
            if not schema_match:
                continue
            table_match = next(
                (
                    table
                    for table in schema_match.get("tables", [])
                    if table.get("table_name", table.get("name", "")) == parsed["table"]
                ),
                None,
            )
            if not table_match:
                continue
            column_match = next(
                (column for column in table_match.get("columns", []) if column.get("name", "") == parsed["column"]),
                None,
            )
            if not column_match:
                continue

            table_annotations = get_table_annotations(annotations, parsed["schema"], parsed["table"])
            contexts.append(
                self._build_catalog_context(
                    catalog=catalog,
                    dataset=parsed["dataset"],
                    kind=parsed["kind"],
                    schema_name=parsed["schema"],
                    table=table_match,
                    column=column_match,
                    table_annotations=table_annotations,
                    ref=ref,
                )
            )

        return contexts

    def _inferred_catalog_contexts(self, term: GlossaryTerm) -> list[dict]:
        project = self._load_project()
        candidates = self._term_lookup_candidates(term)
        if not candidates:
            return []

        contexts: list[dict] = []
        seen_refs: set[str] = set()

        for kind in ("source", "target"):
            catalog_dir = self._catalog_dir(project, kind)
            if not catalog_dir.exists():
                continue

            for catalog_path in sorted(catalog_dir.glob("*.yaml")):
                catalog = load_yaml_cached(catalog_path)
                dataset = catalog_path.stem
                annotations = load_annotations(dataset, catalog_dir)
                for schema in catalog.get("schemas", []):
                    schema_name = schema.get("name", "")
                    for table in schema.get("tables", []):
                        table_name = table.get("table_name", table.get("name", ""))
                        table_annotations = get_table_annotations(annotations, schema_name, table_name)
                        for column in table.get("columns", []):
                            column_name = column.get("name", "")
                            normalized = self._normalize_lookup_text(column_name.replace("_", " "))
                            if normalized not in candidates:
                                continue
                            ref = f"{kind}|{dataset}|{schema_name}.{table_name}.{column_name}"
                            if ref in seen_refs:
                                continue
                            seen_refs.add(ref)
                            contexts.append(
                                self._build_catalog_context(
                                    catalog=catalog,
                                    dataset=dataset,
                                    kind=kind,
                                    schema_name=schema_name,
                                    table=table,
                                    column=column,
                                    table_annotations=table_annotations,
                                    ref=ref,
                                )
                            )
                            if len(contexts) >= 3:
                                return contexts

        return contexts

    def _term_source_context(self, term: GlossaryTerm) -> dict:
        contexts = self._related_catalog_contexts(term.related_objects)
        if not contexts:
            contexts = self._inferred_catalog_contexts(term)
        payload = {
            "current_term": {
                "id": term.id,
                "title": term.title,
                "domain": term.domain,
                "category": term.category,
                "business_description": term.business_description,
                "detailed_description": term.detailed_description,
                "synonyms": list(term.synonyms),
                "tags": list(term.tags),
                "related_objects": list(term.related_objects),
            },
            "related_objects": list(term.related_objects),
            "related_catalog_contexts": contexts,
        }
        if len(contexts) == 1:
            payload.update(contexts[0])
        return payload

    def _create_azure_client(self):
        from dotenv import load_dotenv
        from foundry_client import create_foundry_client

        load_dotenv(_ROOT / ".env")
        agent_cfg = self._load_agent_config()
        api_key_env = agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY")
        api_key = os.environ.get(api_key_env, "")
        endpoint = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
        if not api_key or not endpoint:
            raise RuntimeError(
                "Azure Foundry configuration is missing. Set AZURE_FOUNDRY_KEY and "
                "AZURE_FOUNDRY_ENDPOINT before generating glossary drafts."
            )

        return create_foundry_client(
            api_key=api_key,
            api_key_env=api_key_env,
        )

    @staticmethod
    def _normalise_list(value: object) -> list[str]:
        if isinstance(value, list):
            items = value
        elif isinstance(value, str):
            items = re.split(r"[\n,]", value)
        else:
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    def suggest_term_draft(
        self,
        *,
        title: str,
        domain: str = "",
        category: str = "",
        business_description: str = "",
        detailed_description: str = "",
        synonyms: list[str] | None = None,
        tags: list[str] | None = None,
        source_context: dict | None = None,
    ) -> dict:
        client = self._create_azure_client()
        agent_cfg = self._load_agent_config()
        model = agent_cfg.get("model", "gpt-5.4-mini")
        temperature = agent_cfg.get("temperature", 0)

        prompt = (
            "You draft business glossary terms for a financial data management application. "
            "Return only JSON with keys: title, domain, category, business_description, "
            "detailed_description, synonyms, tags. Use concise, business-friendly language. "
            "Use all available source_context to infer meaning, including column metadata, table metadata, "
            "sample values, profiling statistics, relationships, keys, mapping results, mapping rationales, mapping confidence, transformations, and any user-authored catalog annotations. "
            "When table_columns are provided, use sibling columns to understand the table's business purpose and the column's role within it. "
            "When mapping_contexts are provided, use target concepts, target column names, and mapping rationales to better infer the business meaning of the source field. "
            "If domain or category is uncertain, keep the provided values when present or return an empty string. "
            "If catalog metadata is sparse, infer cautiously from the field name and surrounding context and avoid overstating certainty. "
            "Do not invent steward names, IDs, or regulatory citations that are not implied by the input."
        )
        user_prompt = json.dumps(
            {
                "title": title,
                "domain": domain,
                "category": category,
                "business_description": business_description,
                "detailed_description": detailed_description,
                "synonyms": synonyms or [],
                "tags": tags or [],
                "source_context": source_context or {},
            },
            ensure_ascii=True,
        )

        import time as _time
        t0 = _time.perf_counter()
        response = client.responses.create(
            model=model,
            instructions=prompt,
            input=user_prompt + "\n\nRespond with valid JSON.",
            temperature=temperature,
            text={"format": {"type": "json_object"}},
        )
        latency_ms = (_time.perf_counter() - t0) * 1000
        from core.audit.store import record_ai_call
        usage = getattr(response, "usage", None)
        record_ai_call(
            model=model,
            subject_type="glossary_term",
            subject_id=title,
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            latency_ms=latency_ms,
            prompt_id="glossary_agent.suggest_term_draft",
        )
        raw = json.loads(response.output_text)

        draft = {
            "title": str(raw.get("title") or title).strip(),
            "domain": str(raw.get("domain") or domain).strip(),
            "category": str(raw.get("category") or category).strip(),
            "business_description": str(raw.get("business_description") or "").strip(),
            "detailed_description": str(raw.get("detailed_description") or "").strip(),
            "synonyms": self._normalise_list(raw.get("synonyms")),
            "tags": self._normalise_list(raw.get("tags")),
        }
        draft["ai_generated_fields"] = [
            field
            for field, value in draft.items()
            if field != "ai_generated_fields" and value and (not isinstance(value, list) or value)
        ]
        return draft

    # ------------------------------------------------------------------
    # Future: AI-assisted definition drafting (stub)
    # ------------------------------------------------------------------

    def suggest_definitions(self, term: GlossaryTerm) -> dict[str, str]:
        try:
            draft = self.suggest_term_draft(
                title=term.title,
                domain=term.domain,
                category=term.category,
                business_description=term.business_description,
                detailed_description=term.detailed_description,
                synonyms=term.synonyms,
                tags=term.tags,
                source_context=self._term_source_context(term),
            )
            return {
                "business_description": draft.get("business_description", ""),
                "detailed_description": draft.get("detailed_description", ""),
            }
        except Exception:
            return {"business_description": "", "detailed_description": ""}

    def suggest_term_update(self, term: GlossaryTerm) -> dict:
        return self.suggest_term_draft(
            title=term.title,
            domain=term.domain,
            category=term.category,
            business_description=term.business_description,
            detailed_description=term.detailed_description,
            synonyms=term.synonyms,
            tags=term.tags,
            source_context=self._term_source_context(term),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(description="Business Glossary Agent CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search", metavar="QUERY", help="Full-text search across all terms")
    group.add_argument("--term", metavar="ID", help="Show a single term by id")
    group.add_argument("--list", action="store_true", help="List all terms (id | title)")
    args = parser.parse_args()

    agent = GlossaryAgent()

    if args.list:
        for t in agent.all_terms():
            print(f"{t.id:35s}  [{t.domain} > {t.category}]  {t.title}")

    elif args.search:
        results = agent.search(args.search)
        if not results:
            print("No matching terms found.")
        for t in results:
            print(f"\n{'=' * 60}")
            print(f"  {t.title}  [{t.domain} > {t.category}]")
            print(f"  {t.business_description.strip()}")

    elif args.term:
        t = agent.get(args.term)
        if not t:
            print(f"Term '{args.term}' not found.")
            sys.exit(1)
        print(yaml.dump(t.to_dict(), default_flow_style=False, allow_unicode=True))


if __name__ == "__main__":
    _cli()
