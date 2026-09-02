"""Dashboard API routes — summary statistics for coverage overview."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends

from api.deps import get_paths, get_root
from core.catalog import load_catalog_dispatch
from core.yaml_cache import load_yaml_cached

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    # Mtime-cached — mapping results have no Postgres backend (unlike catalogs, below),
    # so this is the fastest correct read; these files only change on a mapping re-run.
    return load_yaml_cached(path) or {}


def _list_yaml(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.glob("*.yaml")
        if not p.name.endswith(".annotations.yaml")
    )


def _catalog_counts(files: list[Path], *, kind: str) -> dict:
    # Respects catalog_backend (Postgres by default) via the same dispatch every
    # other route uses — this endpoint was the one place still bypassing it and
    # reading the on-disk YAML rollback files directly (the confirmed root cause
    # of a 28-36s dashboard load: ~10MB re-parsed with plain yaml.safe_load on
    # every single call).
    datasets = len(files)
    tables = 0
    columns = 0
    for path in files:
        data = load_catalog_dispatch(path, kind=kind)
        for schema in data.get("schemas", []):
            for table in schema.get("tables", []):
                tables += 1
                columns += len(table.get("columns", []))
    return {"datasets": datasets, "tables": tables, "columns": columns}


def _mapping_detail(files: list[Path]) -> dict:
    total = len(files)
    with_results = 0
    mapped_columns = 0
    derived_columns = 0
    unmapped_columns = 0
    by_source_table: dict[str, dict] = {}
    confidence_bands = {"0.90–1.00": 0, "0.75–0.89": 0, "0.50–0.74": 0, "< 0.50": 0}

    for path in files:
        data = _load_yaml(path)
        mapping_tables = data.get("tables", [])
        if not mapping_tables:
            continue
        with_results += 1
        for tbl in mapping_tables:
            for col in tbl.get("columns", []):
                source_column = col.get("source_column")
                transform = col.get("transformation_type", "")
                confidence = col.get("confidence")

                if source_column:
                    mapped_columns += 1
                else:
                    unmapped_columns += 1
                if transform == "derived":
                    derived_columns += 1

                if confidence is not None:
                    c = float(confidence)
                    if c >= 0.90:
                        confidence_bands["0.90–1.00"] += 1
                    elif c >= 0.75:
                        confidence_bands["0.75–0.89"] += 1
                    elif c >= 0.50:
                        confidence_bands["0.50–0.74"] += 1
                    else:
                        confidence_bands["< 0.50"] += 1

                src_schema = col.get("source_schema", "")
                src_table = col.get("source_table", "")
                if src_schema and src_table:
                    key = f"{src_schema}.{src_table}"
                else:
                    continue

                bucket = by_source_table.setdefault(
                    key,
                    {"columns": 0, "mapped": 0, "unmapped": 0, "confidence_sum": 0.0, "confidence_n": 0},
                )
                bucket["columns"] += 1
                if source_column:
                    bucket["mapped"] += 1
                else:
                    bucket["unmapped"] += 1
                if confidence is not None:
                    bucket["confidence_sum"] += float(confidence)
                    bucket["confidence_n"] += 1

    source_tables = [
        {
            "source_table": k,
            "columns": v["columns"],
            "mapped": v["mapped"],
            "unmapped": v["unmapped"],
            "avg_confidence": round(v["confidence_sum"] / v["confidence_n"], 3) if v["confidence_n"] else 0,
        }
        for k, v in sorted(by_source_table.items())
    ]

    return {
        "total": total,
        "with_results": with_results,
        "mapped_columns": mapped_columns,
        "derived_columns": derived_columns,
        "unmapped_columns": unmapped_columns,
        "confidence_bands": [{"band": b, "columns": c} for b, c in confidence_bands.items()],
        "by_source_table": source_tables,
    }


def _glossary_detail(root: Path) -> dict:
    from core.glossary_db.read_api import glossary_terms
    terms = glossary_terms()

    status_counts = Counter((t.get("status") or "unspecified").title() for t in terms)
    category_counts = Counter(t.get("category") or "Unspecified" for t in terms)

    ai_fields_all = [
        "title", "category", "business_description", "detailed_description",
        "synonyms", "tags", "related_objects",
    ]
    ai_component_counts: Counter[str] = Counter()
    ai_terms = 0
    for t in terms:
        fields = t.get("ai_generated_fields") or []
        if fields:
            ai_terms += 1
        for f in fields:
            ai_component_counts[f] += 1
    n = len(terms) or 1
    ai_components = [
        {"component": f.replace("_", " ").title(), "coverage": round(ai_component_counts.get(f, 0) / n, 3)}
        for f in ai_fields_all
        if ai_component_counts.get(f, 0) > 0 or f in {"title", "category", "business_description"}
    ]

    return {
        "terms": len(terms),
        "ai_terms": ai_terms,
        "by_status": [{"status": s, "count": c} for s, c in sorted(status_counts.items())],
        "by_category": [{"category": cat, "count": c} for cat, c in sorted(category_counts.items())],
        "ai_components": ai_components,
    }


@router.get("/summary")
async def dashboard_summary(
    paths: dict = Depends(get_paths),
    root: Path = Depends(get_root),
):
    source_files = _list_yaml(paths["sources"])
    target_files = _list_yaml(paths["targets"])
    mapping_files = _list_yaml(paths["mappings"])

    return {
        "sources": _catalog_counts(source_files, kind="source"),
        "targets": _catalog_counts(target_files, kind="target"),
        "mappings": _mapping_detail(mapping_files),
        "glossary": _glossary_detail(root),
    }
