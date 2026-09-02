"""Helpers for surfacing source catalog concepts not yet covered in the glossary."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from annotations import get_table_annotations, load_annotations
from catalog_builder import load_project
from yaml_cache import load_yaml_cached

_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CatalogConcept:
    kind: str
    dataset: str
    schema: str
    table: str
    column: str
    data_type: str = ""
    description: str = ""
    table_description: str = ""
    source_context: dict = field(default_factory=dict)

    @property
    def related_object(self) -> str:
        return f"{self.kind}|{self.dataset}|{self.schema}.{self.table}.{self.column}"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _to_title(text: str) -> str:
    words = re.sub(r"([A-Z])", r" \1", text or "").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words)


def _source_catalog_dir(project: dict) -> Path:
    paths = project.get("paths", {})
    return _ROOT / paths.get("source_catalogs", "sources")


def _mappings_dir() -> Path:
    return _ROOT / "mappings"


def _mapping_contexts(*, dataset: str, schema_name: str, table_name: str, column_name: str) -> list[dict]:
    mappings_dir = _mappings_dir()
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


def _build_source_context(
    *,
    catalog: dict,
    dataset: str,
    kind: str,
    schema_name: str,
    table: dict,
    column: dict,
    table_annotations: dict,
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
        "mapping_contexts": _mapping_contexts(
            dataset=dataset,
            schema_name=schema_name,
            table_name=table.get("table_name", table.get("name", "")),
            column_name=column.get("name", ""),
        ),
    }


def _covered_related_objects(terms: list[object]) -> set[str]:
    refs: set[str] = set()
    for term in terms:
        refs.update(getattr(term, "related_objects", []) or [])
    return refs


def _covered_names(terms: list[object]) -> set[str]:
    names: set[str] = set()
    for term in terms:
        candidates = [
            getattr(term, "title", ""),
            getattr(term, "id", ""),
            *(getattr(term, "synonyms", []) or []),
        ]
        for candidate in candidates:
            normalized = _normalize(str(candidate))
            if normalized:
                names.add(normalized)
    return names


def _concept_name_candidates(concept: CatalogConcept) -> set[str]:
    return {
        value
        for value in {
            _normalize(concept.column),
            _normalize(concept.column.replace("_", " ")),
            _normalize(_to_title(concept.column)),
        }
        if value
    }


def find_uncovered_source_concepts(terms: list[object], *, limit: int | None = None) -> list[CatalogConcept]:
    project = load_project()
    source_dir = _source_catalog_dir(project)
    covered_refs = _covered_related_objects(terms)
    covered_names = _covered_names(terms)
    concepts: list[CatalogConcept] = []

    for source_cfg in project.get("sources", []):
        dataset = source_cfg.get("name", "")
        catalog_path = source_dir / f"{dataset}.yaml"
        if not catalog_path.exists():
            continue

        catalog = load_yaml_cached(catalog_path)
        annotations = load_annotations(dataset, source_dir)
        for schema in catalog.get("schemas", []):
            schema_name = schema.get("name", "")
            for table in schema.get("tables", []):
                table_name = table.get("table_name", table.get("name", ""))
                table_description = table.get("description") or ""
                table_annotations = get_table_annotations(annotations, schema_name, table_name)
                for column in table.get("columns", []):
                    concept = CatalogConcept(
                        kind="source",
                        dataset=dataset,
                        schema=schema_name,
                        table=table_name,
                        column=column.get("name", ""),
                        data_type=column.get("data_type", ""),
                        description=column.get("description") or "",
                        table_description=table_description,
                        source_context=_build_source_context(
                            catalog=catalog,
                            dataset=dataset,
                            kind="source",
                            schema_name=schema_name,
                            table=table,
                            column=column,
                            table_annotations=table_annotations,
                        ),
                    )
                    if not concept.column or concept.related_object in covered_refs:
                        continue
                    if _concept_name_candidates(concept) & covered_names:
                        continue
                    concepts.append(concept)

    concepts.sort(key=lambda item: (item.dataset.lower(), item.table.lower(), item.column.lower()))
    if limit is not None:
        return concepts[:limit]
    return concepts


def concept_display_label(concept: CatalogConcept) -> str:
    prefix = f"{concept.schema}." if concept.schema else ""
    data_type = f" [{concept.data_type}]" if concept.data_type else ""
    return f"{prefix}{concept.table}.{concept.column}{data_type}"


def concept_prefill_payload(concept: CatalogConcept) -> dict:
    return {
        "title": _to_title(concept.column),
        "tags": [concept.dataset, concept.table],
        "related_objects": [concept.related_object],
        "source_context": {
            "kind": concept.kind,
            "dataset": concept.dataset,
            "schema": concept.schema,
            "table": concept.table,
            "column": concept.column,
            "data_type": concept.data_type,
            "description": concept.description,
            "table_description": concept.table_description,
            **concept.source_context,
        },
    }