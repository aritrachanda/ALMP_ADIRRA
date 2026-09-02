"""
chat_agent.py — Context-aware conversational agent with tool calling.

Uses the Azure Responses API for multi-turn conversation with LLM-native
tool calling. Tools provide access to project context: glossary, source/target
catalogs, and mapping results.

Usage (from ui/pages/chat.py):
    from chat_agent import chat
    reply = chat(messages, agent_cfg)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import duckdb

import urllib.request
import urllib.parse
import urllib.error

from core.yaml_cache import load_yaml_cached
from core.glossary import load_glossary
from core.bird_kb import bird_conn
from agents.agent_utils.crr_retrieval import search_chunks, lookup_article
from agents.agent_utils.dpm_retrieval import search_dpm as _dpm_search, lookup_table as _dpm_lookup_table, lookup_cells as _dpm_lookup_cells

# Base URL for calling the local FastAPI server from within the agent.
# Agents run in the same process/host as the API, so this is always localhost.
_API_BASE = os.environ.get("AI_TIMO_API_BASE", "http://localhost:8000")


def _api_get(path: str, params: dict | None = None) -> dict:
    """Fetch a JSON response from the local FastAPI server.

    Returns the parsed JSON dict on success, or {"error": "..."} on failure.
    """
    url = _API_BASE.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return {"error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:
        return {"error": str(exc)}

PROJECT_FILE = _ROOT / "project.yaml"
CONNECTIONS_FILE = _ROOT / "connections.yaml"

# CRR3 relevance threshold (L2 distance)
_CRR_MAX_DISTANCE = 1.5


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _load_project() -> dict:
    return load_yaml_cached(PROJECT_FILE)


def _get_paths(project: dict) -> dict:
    paths = project.get("paths", {})
    return {
        "sources": _ROOT / paths.get("source_catalogs", "sources"),
        "targets": _ROOT / paths.get("target_catalogs", "targets"),
        "mappings": _ROOT / paths.get("mappings", "mappings"),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_list_sources() -> str:
    project = _load_project()
    names = [s["name"] for s in project.get("sources", [])]
    return json.dumps({"sources": names})


def _tool_list_targets() -> str:
    project = _load_project()
    names = [t["name"] for t in project.get("targets", [])]
    return json.dumps({"targets": names})


def _tool_list_mappings() -> str:
    paths = _get_paths(_load_project())
    mapping_dir = paths["mappings"]
    if not mapping_dir.exists():
        return json.dumps({"mappings": []})
    files = sorted(f.name for f in mapping_dir.glob("*.yaml"))
    return json.dumps({"mappings": files})


def _tool_get_glossary() -> str:
    """Return glossary summary: list of term IDs grouped by category."""
    data = load_glossary()
    terms = data.get("terms", [])
    categories: dict[str, list[str]] = {}
    for t in terms:
        cat = t.get("category", "Uncategorized")
        categories.setdefault(cat, []).append(t.get("id", ""))
    return json.dumps({
        "total_terms": len(terms),
        "categories": {cat: sorted(ids) for cat, ids in sorted(categories.items())},
        "hint": "Use get_glossary_term to see full details for a specific term.",
    }, indent=2)


def _tool_get_glossary_term(term_id: str) -> str:
    """Return full details for a specific glossary term."""
    data = load_glossary()
    for t in data.get("terms", []):
        if t.get("id", "").lower() == term_id.lower():
            return yaml.dump(t, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return json.dumps({"error": f"Glossary term '{term_id}' not found."})


def _tool_get_source_catalog(source_name: str) -> str:
    """Return summary: list of tables with column counts and descriptions."""
    paths = _get_paths(_load_project())
    path = paths["sources"] / f"{source_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"Source catalog '{source_name}' not found."})
    data = load_yaml_cached(path)
    tables = []
    for schema in data.get("schemas", []):
        for tbl in schema.get("tables", []):
            tables.append({
                "schema": tbl.get("schema_name", ""),
                "table": tbl.get("table_name", ""),
                "description": tbl.get("description", ""),
                "row_count": tbl.get("row_count"),
                "column_count": len(tbl.get("columns", [])),
                "columns": [c["name"] for c in tbl.get("columns", [])],
            })
    return json.dumps({"source": source_name, "tables": tables}, indent=2)


def _tool_get_source_table(source_name: str, table_name: str) -> str:
    """Return full column details for a single source table."""
    paths = _get_paths(_load_project())
    path = paths["sources"] / f"{source_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"Source catalog '{source_name}' not found."})
    data = load_yaml_cached(path)
    for schema in data.get("schemas", []):
        for tbl in schema.get("tables", []):
            if tbl.get("table_name", "").lower() == table_name.lower():
                return yaml.dump(tbl, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return json.dumps({"error": f"Table '{table_name}' not found in source '{source_name}'."})


def _tool_get_target_catalog(target_name: str) -> str:
    """Return summary: list of tables with column counts and descriptions."""
    paths = _get_paths(_load_project())
    path = paths["targets"] / f"{target_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"Target catalog '{target_name}' not found."})
    data = load_yaml_cached(path)
    tables = []
    for schema in data.get("schemas", []):
        for tbl in schema.get("tables", []):
            tables.append({
                "schema": tbl.get("schema_name", ""),
                "table": tbl.get("table_name", ""),
                "description": tbl.get("description", ""),
                "column_count": len(tbl.get("columns", [])),
            })
    return json.dumps({"target": target_name, "table_count": len(tables), "tables": tables}, indent=2)


def _tool_get_target_table(target_name: str, table_name: str) -> str:
    """Return full column details for a single target table."""
    paths = _get_paths(_load_project())
    path = paths["targets"] / f"{target_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"Target catalog '{target_name}' not found."})
    data = load_yaml_cached(path)
    for schema in data.get("schemas", []):
        for tbl in schema.get("tables", []):
            if tbl.get("table_name", "").lower() == table_name.lower():
                return yaml.dump(tbl, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return json.dumps({"error": f"Table '{table_name}' not found in target '{target_name}'."})


def _tool_get_mapping(source_name: str, target_name: str) -> str:
    """Return mapping summary with per-table aggregations. Supports v1 and v2."""
    paths = _get_paths(_load_project())
    path = paths["mappings"] / f"{source_name}_to_{target_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"No mapping found for {source_name} → {target_name}."})
    data = load_yaml_cached(path)
    version = data.get("version", 1)

    summary_tables = []
    if version >= 2:
        # V2: target-centric
        for tbl in data.get("tables", []):
            cols = tbl.get("columns", [])
            mapped = [c for c in cols if c.get("source_column")]
            unmapped = [c for c in cols if not c.get("source_column")]
            source_tables = sorted(set(
                c.get("source_table", "") for c in mapped if c.get("source_table")
            ))
            summary_tables.append({
                "target_table": f"{tbl.get('target_schema', '')}.{tbl.get('target_table', '')}",
                "total_columns": len(cols),
                "mapped": len(mapped),
                "unmapped": len(unmapped),
                "source_tables": source_tables,
                "has_sql": bool(tbl.get("sql_query")),
            })
        return json.dumps({
            "source": source_name,
            "target": target_name,
            "version": version,
            "tables": summary_tables,
            "hint": "Use get_mapping_table to see column-level mapping details for a specific target table.",
        }, indent=2)
    else:
        # V1: source-centric
        for tbl in data.get("tables", []):
            candidates = tbl.get("candidates", [])
            all_cols = []
            for cand in candidates:
                all_cols.extend(cand.get("columns", []))
            mapped = [m for m in all_cols if m.get("target_column")]
            unmapped = [m for m in all_cols if not m.get("target_column")]
            summary_tables.append({
                "source_table": tbl.get("source_table", ""),
                "total_columns": len(all_cols),
                "mapped": len(mapped),
                "unmapped": len(unmapped),
                "target_tables": sorted(set(
                    m.get("target_table", "") for m in mapped if m.get("target_table")
                )),
            })
        return json.dumps({
            "source": source_name,
            "target": target_name,
            "version": version,
            "tables": summary_tables,
            "hint": "Use get_mapping_table to see column-level mapping details for a specific table.",
        }, indent=2)


def _tool_get_mapping_table(source_name: str, target_name: str, table_name: str) -> str:
    """Return column-level mapping details for a specific table. Supports v1 and v2."""
    paths = _get_paths(_load_project())
    path = paths["mappings"] / f"{source_name}_to_{target_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"No mapping found for {source_name} → {target_name}."})
    data = load_yaml_cached(path)
    version = data.get("version", 1)

    if version >= 2:
        # V2: search by target table name
        for tbl in data.get("tables", []):
            if tbl.get("target_table", "").lower() == table_name.lower():
                return yaml.dump(tbl, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return json.dumps({"error": f"No mapping for target table '{table_name}' in {source_name} → {target_name}."})
    else:
        # V1: search by source table name
        for tbl in data.get("tables", []):
            if tbl.get("source_table", "").lower() == table_name.lower():
                return yaml.dump(tbl, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return json.dumps({"error": f"No mapping for table '{table_name}' in {source_name} → {target_name}."})


def _tool_search_column(column_name: str, catalog_type: str = "all", catalog_name: str | None = None) -> str:
    """Search for columns matching a name (substring) across source/target catalogs."""
    paths = _get_paths(_load_project())
    results = []
    search = column_name.lower()

    dirs_to_search = []
    if catalog_type in ("all", "source"):
        if catalog_name:
            dirs_to_search.append(("source", paths["sources"] / f"{catalog_name}.yaml"))
        else:
            dirs_to_search.extend(("source", p) for p in paths["sources"].glob("*.yaml"))
    if catalog_type in ("all", "target"):
        if catalog_name:
            dirs_to_search.append(("target", paths["targets"] / f"{catalog_name}.yaml"))
        else:
            dirs_to_search.extend(("target", p) for p in paths["targets"].glob("*.yaml"))

    for cat_type, path in dirs_to_search:
        if not path.exists():
            continue
        data = load_yaml_cached(path)
        cat_name = path.stem
        for schema in data.get("schemas", []):
            for tbl in schema.get("tables", []):
                for col in tbl.get("columns", []):
                    if search in col.get("name", "").lower():
                        results.append({
                            "catalog_type": cat_type,
                            "catalog": cat_name,
                            "table": tbl.get("table_name", ""),
                            "column": col.get("name", ""),
                            "data_type": col.get("data_type", ""),
                            "description": col.get("description", ""),
                        })

    return json.dumps({"search": column_name, "matches": len(results), "results": results}, indent=2)


def _tool_get_column(catalog_type: str, catalog_name: str, table_name: str, column_name: str) -> str:
    """Return full metadata for a single column."""
    paths = _get_paths(_load_project())
    dir_key = "sources" if catalog_type == "source" else "targets"
    path = paths[dir_key] / f"{catalog_name}.yaml"
    if not path.exists():
        return json.dumps({"error": f"Catalog '{catalog_name}' not found."})
    data = load_yaml_cached(path)
    for schema in data.get("schemas", []):
        for tbl in schema.get("tables", []):
            if tbl.get("table_name", "").lower() != table_name.lower():
                continue
            for col in tbl.get("columns", []):
                if col.get("name", "").lower() == column_name.lower():
                    return yaml.dump(col, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return json.dumps({"error": f"Column '{column_name}' not found in {catalog_type}/{catalog_name}/{table_name}."})


# ---------------------------------------------------------------------------
# Live API tools — call the running FastAPI server for real-time governance data
# ---------------------------------------------------------------------------

def _tool_get_governance_summary() -> str:
    """Return aggregated platform-wide governance + mapping metrics from the dashboard."""
    data = _api_get("/api/dashboard/summary")
    if "error" in data:
        return json.dumps(data)
    return json.dumps(data, indent=2)


def _tool_get_source_overview(source_name: str) -> str:
    """Return source-level governance rollup: dataset count, column count, governance state
    breakdown (draft/defined/approved), semantic type mix, and per-dataset summary."""
    data = _api_get(f"/api/element/{source_name}/info")
    if "error" in data:
        return json.dumps(data)
    # Return a focused subset to keep context lean
    out = {
        "source": data.get("source"),
        "table_count": data.get("table_count"),
        "column_count": data.get("column_count"),
        "governance_state": data.get("governance_state"),
        "semantic_type_mix": data.get("semantic_type_mix"),
        "datasets": [
            {
                "table_name": d.get("table_name"),
                "schema": d.get("schema"),
                "row_count": d.get("row_count"),
                "column_count": d.get("column_count"),
                "has_story": d.get("has_story"),
                "story_is_ai": d.get("story_is_ai"),
                "governance": d.get("governance"),
            }
            for d in (data.get("datasets") or [])
        ],
    }
    return json.dumps(out, indent=2)


def _tool_get_dataset_overview(source_name: str, table_name: str, schema: str | None = None) -> str:
    """Return dataset-level governance rollup: row/col count, completeness, governance state
    breakdown, semantic type mix, observation matrix, and per-column lifecycle/quality summary."""
    params = {"schema": schema} if schema else None
    data = _api_get(f"/api/element/{source_name}/{table_name}/overview", params)
    if "error" in data:
        return json.dumps(data)
    out = {
        "source": data.get("source"),
        "schema": data.get("schema"),
        "table_name": data.get("table_name"),
        "row_count": data.get("row_count"),
        "column_count": data.get("column_count"),
        "completeness": data.get("completeness"),
        "governance_state": data.get("governance_state"),
        "semantic_type_mix": data.get("semantic_type_mix"),
        "observation_matrix": data.get("observation_matrix"),
        "primary_key": data.get("primary_key"),
        "columns_summary": [
            {
                "name": c.get("name"),
                "data_type": c.get("data_type"),
                "semantic_type": c.get("semantic_type"),
                "semantic_domain_role": c.get("semantic_domain_role"),
                "lifecycle_state": c.get("lifecycle_state"),
                "quality_grade": c.get("quality_grade"),
                "completeness": c.get("completeness"),
                "observation_count": c.get("observation_count"),
                "description": c.get("description"),
                "description_is_ai": c.get("description_is_ai"),
                "business_name": c.get("business_name"),
                "business_name_is_ai": c.get("business_name_is_ai"),
            }
            for c in (data.get("columns_summary") or [])
        ],
    }
    return json.dumps(out, indent=2)


def _tool_get_element_detail(source_name: str, table_name: str, column_name: str, schema: str | None = None) -> str:
    """Return full governance detail for a single column element: lifecycle state, quality grade,
    AI-generated definition, business name, observations/findings, mapping candidates,
    linked glossary term, and audit history."""
    params = {"schema": schema} if schema else None
    data = _api_get(f"/api/element/{source_name}/{table_name}/{column_name}", params)
    if "error" in data:
        return json.dumps(data)
    return json.dumps(data, indent=2)


def _tool_get_audit_events(
    event_class: str | None = None,
    event_type: str | None = None,
    subject_type: str | None = None,
    limit: int = 20,
) -> str:
    """Return recent audit events from the governance audit log.
    Use event_class to filter by 'governance', 'ai', 'system', 'data', or 'user'.
    Use event_type to filter by specific action (e.g. 'element.state.changed', 'ai.description.generated').
    Returns events in reverse-chronological order."""
    params = {
        "limit": limit,
        "event_class": event_class,
        "event_type": event_type,
        "subject_type": subject_type,
    }
    data = _api_get("/api/audit/events", params)
    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)
    return json.dumps({"events": data, "count": len(data) if isinstance(data, list) else 0}, indent=2)


def _tool_get_audit_summary(days: int = 30) -> str:
    """Return a summary of governance activity over the past N days: event counts by type and class.
    Good for answering 'what happened recently?' or 'how active has governance been?'"""
    data = _api_get("/api/audit/summary", {"days": days})
    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)
    return json.dumps({"period_days": days, "summary": data}, indent=2)


def _tool_get_insights(source_name: str, table_name: str) -> str:
    """Return structured AI-generated data quality insights for a dataset: findings with severity
    (critical/high/medium/low), rule-based vs AI-detected classification, rationale, regulatory
    notes, and submission readiness score."""
    data = _api_get(f"/api/insights/{source_name}/{table_name}")
    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)
    return json.dumps(data, indent=2)


def _tool_get_glossary_gaps() -> str:
    """Return a list of source columns that have no linked glossary term — the 'coverage gaps'
    in business context. Useful for answering 'which fields still need business definitions?'"""
    data = _api_get("/api/glossary/uncovered")
    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)
    return json.dumps(data, indent=2)


def _tool_search_crr(query: str) -> str:
    """Semantic search over CRR3 regulation text. Returns top-k relevant chunks."""
    results = search_chunks(query, k=5, max_distance=_CRR_MAX_DISTANCE)
    if not results:
        return json.dumps({"query": query, "matches": 0, "results": [], "message": "No relevant CRR3 content found for this query."})
    return json.dumps({
        "query": query,
        "matches": len(results),
        "results": [{"text": r["text"], "distance": round(r["distance"], 3)} for r in results],
    }, indent=2)


def _tool_get_crr_article(article_num: str) -> str:
    """Retrieve a specific CRR3 article by number."""
    result = lookup_article(article_num)
    if result is None:
        return json.dumps({"error": f"CRR3 Article {article_num} not found."})
    return json.dumps({
        "article_num": result["article_num"],
        "headline": result["headline"],
        "text": result["text"],
    }, indent=2)


# DPM relevance threshold (L2 distance)
_DPM_MAX_DISTANCE = 1.6

def _tool_search_dpm(query: str) -> str:
    """Semantic search over EBA DPM 2.0 datapoints. Returns top-k matching chunks."""
    results = _dpm_search(query, k=8, max_distance=_DPM_MAX_DISTANCE)
    if not results:
        return json.dumps({"query": query, "matches": 0, "results": [], "message": "No relevant DPM datapoints found for this query."})
    return json.dumps({
        "query": query,
        "matches": len(results),
        "results": [{"text": r["text"], "distance": round(r["distance"], 3)} for r in results],
    }, indent=2)


def _tool_get_dpm_table(table_code: str) -> str:
    """Retrieve metadata for a specific DPM table by code."""
    result = _dpm_lookup_table(table_code)
    if result is None:
        return json.dumps({"error": f"DPM table '{table_code}' not found."})
    return json.dumps(result, indent=2)


def _tool_get_dpm_cells(table_code: str, keyword: str | None = None) -> str:
    """Look up exact cell coordinates for a DPM table, optionally filtered by keyword."""
    results = _dpm_lookup_cells(table_code, keyword)
    if results is None:
        return json.dumps({"error": f"DPM table '{table_code}' not found in cell lookup."})
    if not results:
        return json.dumps({"table_code": table_code, "keyword": keyword, "matches": 0, "cells": [], "message": "No cells matched the keyword filter."})
    return json.dumps({"table_code": table_code, "keyword": keyword, "matches": len(results), "cells": results[:50]}, indent=2)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

_MAX_QUERY_ROWS = 1000


def _resolve_duckdb_path(connection_name: str) -> Path | str:
    """Resolve a connection name to an absolute DuckDB file path.

    Returns the Path on success, or an error string on failure.
    """
    data = load_yaml_cached(CONNECTIONS_FILE)
    connections = data.get("connections", [])
    duckdb_names = []
    for conn in connections:
        if conn.get("type") == "duckdb":
            duckdb_names.append(conn["name"])
            if conn["name"].lower() == connection_name.lower():
                db_path = _ROOT / conn["database"]
                if not db_path.exists():
                    return f"Database file not found: {db_path}"
                return db_path.resolve()
    if duckdb_names:
        return f"Connection '{connection_name}' is not a DuckDB connection. Available DuckDB connections: {', '.join(duckdb_names)}"
    return f"No DuckDB connections found in connections.yaml."


def _tool_query_data(sql: str, connection_name: str) -> str:
    """Execute a read-only SQL query against a DuckDB database."""
    resolved = _resolve_duckdb_path(connection_name)
    if isinstance(resolved, str):
        return json.dumps({"error": resolved})
    try:
        conn = duckdb.connect(str(resolved), read_only=True)
        try:
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchmany(_MAX_QUERY_ROWS + 1)
            truncated = len(rows) > _MAX_QUERY_ROWS
            if truncated:
                rows = rows[:_MAX_QUERY_ROWS]
            data = [dict(zip(columns, row)) for row in rows]
            out: dict = {"columns": columns, "row_count": len(data), "data": data}
            if truncated:
                out["truncated"] = True
                out["message"] = f"Result truncated to {_MAX_QUERY_ROWS} rows."
            return json.dumps(out, indent=2, default=str)
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"error": f"SQL error: {exc}"})


_VALID_CHART_TYPES = {"bar", "line", "scatter", "pie", "histogram"}


def _tool_render_chart(
    chart_type: str,
    title: str,
    x: str,
    y: str,
    data_sql: str,
    connection_name: str,
    color: str | None = None,
) -> str:
    """Return a structured chart spec for the UI to render."""
    if chart_type not in _VALID_CHART_TYPES:
        return json.dumps({
            "error": f"Unsupported chart type '{chart_type}'. Supported types: {', '.join(sorted(_VALID_CHART_TYPES))}"
        })
    spec: dict = {
        "chart_type": chart_type,
        "title": title,
        "x": x,
        "y": y,
        "data_sql": data_sql,
        "connection_name": connection_name,
    }
    if color:
        spec["color"] = color
    return json.dumps({"chart_spec": spec})


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

_TOOL_DISPATCH = {
    "list_sources": lambda args: _tool_list_sources(),
    "list_targets": lambda args: _tool_list_targets(),
    "list_mappings": lambda args: _tool_list_mappings(),
    "get_glossary": lambda args: _tool_get_glossary(),
    "get_glossary_term": lambda args: _tool_get_glossary_term(args["term_id"]),
    "get_source_catalog": lambda args: _tool_get_source_catalog(args["source_name"]),
    "get_source_table": lambda args: _tool_get_source_table(args["source_name"], args["table_name"]),
    "get_target_catalog": lambda args: _tool_get_target_catalog(args["target_name"]),
    "get_target_table": lambda args: _tool_get_target_table(args["target_name"], args["table_name"]),
    "get_mapping": lambda args: _tool_get_mapping(args["source_name"], args["target_name"]),
    "get_mapping_table": lambda args: _tool_get_mapping_table(args["source_name"], args["target_name"], args["table_name"]),
    "search_column": lambda args: _tool_search_column(args["column_name"], args.get("catalog_type", "all"), args.get("catalog_name")),
    "get_column": lambda args: _tool_get_column(args["catalog_type"], args["catalog_name"], args["table_name"], args["column_name"]),
    "search_crr": lambda args: _tool_search_crr(args["query"]),
    "get_crr_article": lambda args: _tool_get_crr_article(args["article_num"]),
    "search_dpm": lambda args: _tool_search_dpm(args["query"]),
    "get_dpm_table": lambda args: _tool_get_dpm_table(args["table_code"]),
    "get_dpm_cells": lambda args: _tool_get_dpm_cells(args["table_code"], args.get("keyword")),
    "query_data": lambda args: _tool_query_data(args["sql"], args["connection_name"]),
    "render_chart": lambda args: _tool_render_chart(
        args["type"], args["title"], args["x"], args["y"],
        args["data_sql"], args["connection_name"], args.get("color"),
    ),
    # Live governance API tools
    "get_governance_summary": lambda args: _tool_get_governance_summary(),
    "get_source_overview": lambda args: _tool_get_source_overview(args["source_name"]),
    "get_dataset_overview": lambda args: _tool_get_dataset_overview(args["source_name"], args["table_name"], args.get("schema")),
    "get_element_detail": lambda args: _tool_get_element_detail(args["source_name"], args["table_name"], args["column_name"], args.get("schema")),
    "get_audit_events": lambda args: _tool_get_audit_events(args.get("event_class"), args.get("event_type"), args.get("subject_type"), args.get("limit", 20)),
    "get_audit_summary": lambda args: _tool_get_audit_summary(args.get("days", 30)),
    "get_insights": lambda args: _tool_get_insights(args["source_name"], args["table_name"]),
    "get_glossary_gaps": lambda args: _tool_get_glossary_gaps(),
    "search_bird_entity": lambda args: _tool_search_bird_entity(args["entity_name"], args.get("layer", "LDM")),
    "get_bird_entity_detail": lambda args: _tool_get_bird_entity_detail(args["cube_id"]),
}


# ---------------------------------------------------------------------------
# BIRD KB tool implementations
# ---------------------------------------------------------------------------

_BIRD_ROLE_LABEL = {"D": "Dimension (primary key set)", "O": "Observation (reported fact)", "A": "Attribute (qualifier)"}
_BIRD_LAYER_DESC = {
    "LDM":  "Logical Data Model — canonical business concepts (primary mapping target)",
    "ELDM": "Extended LDM — enriched input layer with additional regulatory concepts",
    "IL":   "Input Layer — WUDEN structural reshape from LDM",
    "EIL":  "Extended Input Layer — DER derivations on the IL",
    "ROL":  "Regulatory Output Layer — final AnaCredit GEN output",
}
_BIRD_LAYER_FILTER = {
    "LDM":  ("cube_type", "LDM"),
    "ELDM": ("cube_type", "ELDM"),
    "IL":   ("cube_type", "IL"),
    "EIL":  ("cube_type", "EIL"),
    "ROL":  ("framework_id", "ANCRDT"),
}


def _tool_search_bird_entity(entity_name: str, layer: str = "LDM") -> str:
    """Search BIRD KB for entities matching entity_name in the given layer."""
    col, val = _BIRD_LAYER_FILTER.get(layer.upper(), ("cube_type", layer.upper()))
    try:
        with bird_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT c.cube_id, c.code, c.name, c.cube_type, c.framework_id, c.description,
                       cg.name AS group_name
                FROM cube_current c
                LEFT JOIN cube_group_enumeration_current cge ON cge.cube_id = c.cube_id
                LEFT JOIN cube_group cg ON cg.cube_group_id = cge.cube_group_id
                WHERE c.{col} = ? AND c.name ILIKE ?
                ORDER BY c.name
                LIMIT 10
                """,
                [val, f"%{entity_name}%"],
            ).fetchall()
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    if not rows:
        return json.dumps({
            "message": f"No BIRD entity found matching '{entity_name}' in layer {layer}.",
            "hint": "Try a shorter term or check the layer (LDM, ELDM, IL, EIL, ROL).",
        })

    layer_note = _BIRD_LAYER_DESC.get(layer.upper(), layer)
    entities = [
        {
            "cube_id": r[0],
            "code": r[1],
            "name": r[2],
            "layer": r[3],
            "framework": r[4],
            "description": r[5] or "",
            "entity_group": r[6] or "",
        }
        for r in rows
    ]
    return json.dumps({
        "layer": layer,
        "layer_description": layer_note,
        "note": "These are BIRD structural reference-model entities — not source database tables.",
        "entities": entities,
        "hint": "Use get_bird_entity_detail with cube_id to see key fields, reported values and qualifiers.",
    }, indent=2)


def _tool_get_bird_entity_detail(cube_id: str) -> str:
    """Return full attribute breakdown of a BIRD entity (D/O/A roles, domains, code lists)."""
    try:
        with bird_conn() as conn:
            cube_row = conn.execute(
                "SELECT cube_id, code, name, cube_type, framework_id, description FROM cube WHERE cube_id = ?",
                [cube_id],
            ).fetchone()
            if not cube_row:
                return json.dumps({"error": f"Entity '{cube_id}' not found."})

            cube = dict(zip(["cube_id", "code", "name", "layer", "framework", "description"], cube_row))

            attr_rows = conn.execute(
                """
                SELECT csi.role, v.code AS var_code, v.name AS var_name,
                       d.name AS domain_name, d.data_type, d.is_enumerated, csi.is_mandatory
                FROM cube_structure_item csi
                JOIN variable v ON v.variable_id = csi.variable_id
                JOIN domain d   ON d.domain_id   = v.domain_id
                WHERE csi.cube_structure_id = (SELECT cube_structure_id FROM cube WHERE cube_id = ?)
                ORDER BY CASE csi.role WHEN 'D' THEN 1 WHEN 'O' THEN 2 WHEN 'A' THEN 3 ELSE 4 END,
                         csi."order"
                """,
                [cube_id],
            ).fetchall()
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    by_role: dict[str, list] = {"D": [], "O": [], "A": []}
    for r in attr_rows:
        role, var_code, var_name, dom_name, data_type, is_enum, is_mand = r
        role = role or "?"
        by_role.setdefault(role, []).append({
            "code": var_code,
            "name": var_name,
            "domain": dom_name,
            "data_type": data_type,
            "enumerated": bool(is_enum),
            "mandatory": bool(is_mand),
        })

    return json.dumps({
        "entity": cube,
        "layer_description": _BIRD_LAYER_DESC.get(cube.get("layer", ""), cube.get("layer", "")),
        "note": "This is a BIRD structural reference-model entity — not a source database table.",
        "key_fields": {"role": "D — Key field (primary key set)", "attributes": by_role.get("D", [])},
        "reported_values": {"role": "O — Reported value (facts to be reported)", "attributes": by_role.get("O", [])},
        "qualifiers": {"role": "A — Qualifier (context for O-role values)", "count": len(by_role.get("A", []))},
        "total_attributes": len(attr_rows),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool definitions (Azure Responses API format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "list_sources",
        "description": "List the names of all source datasets defined in the project.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "list_targets",
        "description": "List the names of all target data models defined in the project.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "list_mappings",
        "description": "List the filenames of all existing mapping YAML files.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_glossary",
        "description": "Return a summary of the business glossary: term IDs grouped by category. Use get_glossary_term for full details on a specific term.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_glossary_term",
        "description": "Return full details for a specific glossary term including descriptions, synonyms, and related objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "term_id": {
                    "type": "string",
                    "description": "ID of the glossary term (e.g. 'annual_turnover').",
                },
            },
            "required": ["term_id"],
        },
    },
    {
        "type": "function",
        "name": "get_source_catalog",
        "description": "Return a summary of a source dataset: list of tables with column names and counts. Use get_source_table for full column details.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the source dataset (e.g. 'banking').",
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "type": "function",
        "name": "get_source_table",
        "description": "Return full column details (data types, profiling stats, sample values) for a single source table.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the source dataset (e.g. 'banking').",
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (e.g. 'counterparties').",
                },
            },
            "required": ["source_name", "table_name"],
        },
    },
    {
        "type": "function",
        "name": "get_target_catalog",
        "description": "Return a summary of a target data model: list of tables with descriptions and column counts. Use get_target_table for full column details.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of the target data model (e.g. 'bird', 'crdm').",
                },
            },
            "required": ["target_name"],
        },
    },
    {
        "type": "function",
        "name": "get_target_table",
        "description": "Return full column details (data types, descriptions, keys) for a single target table.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of the target data model (e.g. 'bird', 'crdm').",
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (e.g. 'PRTY').",
                },
            },
            "required": ["target_name", "table_name"],
        },
    },
    {
        "type": "function",
        "name": "get_mapping",
        "description": "Return a summary of an existing mapping between source and target: per-table mapped/unmapped column counts. Use get_mapping_table for column-level details.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the source dataset.",
                },
                "target_name": {
                    "type": "string",
                    "description": "Name of the target data model.",
                },
            },
            "required": ["source_name", "target_name"],
        },
    },
    {
        "type": "function",
        "name": "get_mapping_table",
        "description": "Return column-level mapping details for a specific source table in a mapping.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the source dataset.",
                },
                "target_name": {
                    "type": "string",
                    "description": "Name of the target data model.",
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the source table to get mapping details for.",
                },
            },
            "required": ["source_name", "target_name", "table_name"],
        },
    },
    {
        "type": "function",
        "name": "search_column",
        "description": "Search for columns by name (substring match) across source and/or target catalogs. Returns matching column names, tables, data types, and descriptions.",
        "parameters": {
            "type": "object",
            "properties": {
                "column_name": {
                    "type": "string",
                    "description": "Column name or partial name to search for (e.g. 'repayment', 'interest_rate').",
                },
                "catalog_type": {
                    "type": "string",
                    "enum": ["all", "source", "target"],
                    "description": "Search in sources, targets, or both. Defaults to 'all'.",
                },
                "catalog_name": {
                    "type": "string",
                    "description": "Optional: restrict search to a specific catalog (e.g. 'crdm', 'banking').",
                },
            },
            "required": ["column_name"],
        },
    },
    {
        "type": "function",
        "name": "get_column",
        "description": "Return full metadata for a single column in a source or target table, including data type, description, profiling stats, and sample values.",
        "parameters": {
            "type": "object",
            "properties": {
                "catalog_type": {
                    "type": "string",
                    "enum": ["source", "target"],
                    "description": "Whether to look in a source or target catalog.",
                },
                "catalog_name": {
                    "type": "string",
                    "description": "Name of the catalog (e.g. 'banking', 'crdm').",
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the table containing the column.",
                },
                "column_name": {
                    "type": "string",
                    "description": "Exact name of the column.",
                },
            },
            "required": ["catalog_type", "catalog_name", "table_name", "column_name"],
        },
    },
    {
        "type": "function",
        "name": "search_crr",
        "description": "Semantic search over CRR3 (EU Regulation 2024/1623) text. Use when the user asks about regulatory definitions, capital requirements, risk weights, or any CRR3-related topic. Returns the most relevant regulation text chunks.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query about CRR3 regulation (e.g. 'own funds requirements', 'definition of default').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_crr_article",
        "description": "Retrieve the full text of a specific CRR3 article by number. Use when the user asks about a specific article (e.g. 'Article 92').",
        "parameters": {
            "type": "object",
            "properties": {
                "article_num": {
                    "type": "string",
                    "description": "The article number (e.g. '92', '4', '5a').",
                },
            },
            "required": ["article_num"],
        },
    },
    {
        "type": "function",
        "name": "query_data",
        "description": "Execute a read-only SQL query against a DuckDB source database. Use when the user asks to see actual data, row counts, aggregations, or wants to explore data values. Returns rows as JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute (e.g. 'SELECT * FROM src.accounts LIMIT 10'). Must be valid DuckDB SQL.",
                },
                "connection_name": {
                    "type": "string",
                    "description": "Name of the database connection from connections.yaml (e.g. 'banking').",
                },
            },
            "required": ["sql", "connection_name"],
        },
    },
    {
        "type": "function",
        "name": "render_chart",
        "description": "Create a chart visualization from data. Returns a chart spec that the UI renders as an interactive Plotly chart. Use when the user asks for a plot, chart, graph, or visualization.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["bar", "line", "scatter", "pie", "histogram"],
                    "description": "Chart type.",
                },
                "title": {
                    "type": "string",
                    "description": "Chart title.",
                },
                "x": {
                    "type": "string",
                    "description": "Column name for x-axis (or 'names' for pie chart).",
                },
                "y": {
                    "type": "string",
                    "description": "Column name for y-axis (or 'values' for pie chart).",
                },
                "data_sql": {
                    "type": "string",
                    "description": "SQL query to fetch the chart data. Must return at least the columns referenced by x and y.",
                },
                "connection_name": {
                    "type": "string",
                    "description": "Name of the database connection from connections.yaml.",
                },
                "color": {
                    "type": "string",
                    "description": "Optional column name for color grouping.",
                },
            },
            "required": ["type", "title", "x", "y", "data_sql", "connection_name"],
        },
    },
    {
        "type": "function",
        "name": "search_dpm",
        "description": "Semantic search over EBA DPM 2.0 (Data Point Model) datapoints. Use when the user asks about EBA reporting templates, COREP/FINREP tables, or where specific data is reported. Returns matching table codes, datapoint paths, and distances.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query about DPM datapoints (e.g. 'Loss Given Default', 'credit risk exposures retail').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_dpm_table",
        "description": "Retrieve metadata for a specific EBA DPM table by its code. Returns the table name, group, cell count, and list of concepts. Use after search_dpm to get more detail about a specific table.",
        "parameters": {
            "type": "object",
            "properties": {
                "table_code": {
                    "type": "string",
                    "description": "The DPM table code (e.g. 'C_08.01.a', 'F_18.00.a').",
                },
            },
            "required": ["table_code"],
        },
    },
    {
        "type": "function",
        "name": "get_dpm_cells",
        "description": "Look up exact cell coordinates (row/column codes) for a DPM table. Returns cell references like {C_08.01.a, r0010, c0060} with their datapoint paths. Use after search_dpm to get precise cell codes for reporting.",
        "parameters": {
            "type": "object",
            "properties": {
                "table_code": {
                    "type": "string",
                    "description": "The DPM table code (e.g. 'C_08.01.a', 'F_18.00.a').",
                },
                "keyword": {
                    "type": "string",
                    "description": "Optional keyword to filter cells by datapoint content (e.g. 'Loss Given Default', 'exposure'). Case-insensitive substring match.",
                },
            },
            "required": ["table_code"],
        },
    },
    # ── Live governance API tools ─────────────────────────────────────────
    {
        "type": "function",
        "name": "get_governance_summary",
        "description": "Return aggregated platform-wide governance and mapping metrics: total datasets, columns, governance state breakdown (draft/defined/approved), mapping coverage percentage, glossary coverage, and AI assistance statistics. Use when the user asks about overall platform health, coverage, or dashboard metrics.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_source_overview",
        "description": "Return source-level governance rollup for a data source: dataset count, total columns, governance state breakdown (draft/defined/approved), semantic type mix, and a per-dataset summary including whether each dataset has a data story. Use when the user asks about the governance status or coverage of a whole source.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "Name of the source (e.g. 'banking', 'Faker')."},
            },
            "required": ["source_name"],
        },
    },
    {
        "type": "function",
        "name": "get_dataset_overview",
        "description": "Return dataset-level governance summary for one table: row/column count, completeness, governance state breakdown, semantic type mix, observation matrix, and per-column lifecycle state, quality grade, completeness, definition, and business name. Use when the user asks about the governance status or quality of a specific dataset.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "Name of the source (e.g. 'banking')."},
                "table_name": {"type": "string", "description": "Name of the table (e.g. 'bank_loans')."},
                "schema": {"type": "string", "description": "Optional schema name if the source has multiple schemas."},
            },
            "required": ["source_name", "table_name"],
        },
    },
    {
        "type": "function",
        "name": "get_element_detail",
        "description": "Return full governance detail for a single column element: lifecycle state, quality grade, AI-generated definition, business name, AI-generated flags, observations and findings, mapping candidates with confidence scores, linked glossary term, and full audit history. Use when the user asks about a specific column's governance status, definition, quality issues, or how it maps to a target model.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "Name of the source (e.g. 'banking')."},
                "table_name": {"type": "string", "description": "Name of the table containing the column."},
                "column_name": {"type": "string", "description": "Exact name of the column."},
                "schema": {"type": "string", "description": "Optional schema name."},
            },
            "required": ["source_name", "table_name", "column_name"],
        },
    },
    {
        "type": "function",
        "name": "get_audit_events",
        "description": "Return recent events from the governance audit log. Use when the user asks what governance activity has happened, who approved something, when a definition was changed, or what AI actions were taken. Filter by event_class ('governance', 'ai', 'system', 'data', 'user') or event_type (e.g. 'element.state.changed', 'ai.description.generated').",
        "parameters": {
            "type": "object",
            "properties": {
                "event_class": {"type": "string", "description": "Filter by class: 'governance', 'ai', 'system', 'data', or 'user'."},
                "event_type": {"type": "string", "description": "Filter by specific event type (e.g. 'element.state.changed')."},
                "subject_type": {"type": "string", "description": "Filter by subject type (e.g. 'element', 'glossary_term')."},
                "limit": {"type": "integer", "description": "Max events to return (default 20, max 100)."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_audit_summary",
        "description": "Return a day-by-day summary of governance activity counts over the past N days. Use to answer 'what governance activity happened this week/month?' or to give an overview of recent platform activity.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look back (default 30)."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_insights",
        "description": "Return structured AI-generated data quality insights for a dataset: findings with severity (critical/high/medium/low), rule-based vs AI-detected classification, rationale, evidence, regulatory notes, and overall submission readiness score. Use when the user asks about data quality issues, anomalies, or whether a dataset is ready for regulatory submission.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "Name of the source (e.g. 'banking')."},
                "table_name": {"type": "string", "description": "Name of the table to get insights for."},
            },
            "required": ["source_name", "table_name"],
        },
    },
    {
        "type": "function",
        "name": "get_glossary_gaps",
        "description": "Return source columns that have no linked glossary term — the business context coverage gaps. Use when the user asks 'which fields have no business definition?', 'what columns are not covered by the glossary?', or wants to know what still needs to be linked.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    # ── BIRD Knowledge Base ──────────────────────────────────────────────
    {
        "type": "function",
        "name": "search_bird_entity",
        "description": (
            "Search for a BIRD entity (cube) by name in the BIRD Knowledge Base (LDM, ELDM, IL, EIL, ROL). "
            "Use this when the user asks about a BIRD LDM or ELDM concept, entity, variable, or domain — "
            "for example 'explain the PARTY entity', 'what attributes does Instrument have?', "
            "'what is the PRTY cube?'. "
            "IMPORTANT: BIRD entities are structural reference-model concepts, NOT source database tables. "
            "Never confuse them with tables in source schemas like E_INPUT or DWH."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name or partial name of the BIRD entity (e.g. 'Party', 'Instrument', 'Collateral').",
                },
                "layer": {
                    "type": "string",
                    "description": "BIRD layer to search: LDM (default), ELDM, IL, EIL, or ROL.",
                    "enum": ["LDM", "ELDM", "IL", "EIL", "ROL"],
                },
            },
            "required": ["entity_name"],
        },
    },
    {
        "type": "function",
        "name": "get_bird_entity_detail",
        "description": (
            "Get full structural detail of a BIRD entity by its ID: key fields (D-role), "
            "reported values (O-role), qualifiers (A-role), domain info, and enumerated code lists. "
            "Use after search_bird_entity to get the full attribute breakdown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cube_id": {
                    "type": "string",
                    "description": "BIRD cube ID returned by search_bird_entity.",
                },
            },
            "required": ["cube_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Persona helpers
# ---------------------------------------------------------------------------

def _load_persona() -> dict:
    """Read persona.yaml fresh on every call — no cache — so runtime edits apply immediately."""
    _defaults: dict = {
        "name": "Assistant",
        "role": "Senior Data Governance Analyst and AI assistant",
        "expertise": [],
        "tone": "precise",
        "verbosity": "balanced",
        "response_format": "prose",
        "avatar_url": "",
        "context": {
            "glossary_links": True,
            "mapping_candidates": True,
            "profiling_stats": True,
            "audit_history": False,
        },
        "knowledge_sources": {
            "crr3_regulation": True,
            "eba_dpm": True,
            "internal_kb": False,
            "policy_documents": False,
        },
        "inference": {
            "temperature": None,
        },
    }
    persona_path = _ROOT / "persona.yaml"
    if not persona_path.exists():
        return {**_defaults}
    with persona_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    merged = {**_defaults, **data}
    merged["context"] = {**_defaults["context"], **data.get("context", {})}
    merged["knowledge_sources"] = {**_defaults["knowledge_sources"], **data.get("knowledge_sources", {})}
    merged["inference"] = {**_defaults["inference"], **data.get("inference", {})}
    return merged


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    project = _load_project()
    persona = _load_persona()
    source_names = [s["name"] for s in project.get("sources", [])]
    target_names = [t["name"] for t in project.get("targets", [])]

    _name = persona.get("name", "Assistant")
    _role = persona.get("role", "Senior Data Governance Analyst and AI assistant")
    _exp = persona.get("expertise", [])
    _tone = persona.get("tone", "precise")
    _verbosity = persona.get("verbosity", "balanced")
    _fmt = persona.get("response_format", "prose")
    _ctx = persona.get("context", {})
    _ks = persona.get("knowledge_sources", {})

    _expertise_line = (
        f" Your specialist areas include: {', '.join(_exp)}." if _exp else ""
    )
    _tone_map = {
        "precise": "Be accurate and precise — prefer specific, verifiable facts over generalities.",
        "friendly": "Be warm, approachable, and encouraging. Use conversational, accessible language.",
        "formal": "Maintain a formal, professional tone. Avoid contractions and colloquialisms.",
        "concise": "Be brief and direct. Lead with the answer, then add supporting detail only if needed.",
    }
    _verbosity_map = {
        "terse": "Keep answers short — one to three sentences where possible. Omit background unless asked.",
        "balanced": "Provide a thorough answer but avoid unnecessary padding or repetition.",
        "detailed": "Give comprehensive answers with context, caveats, and examples where helpful.",
    }
    _format_map = {
        "prose": "Present answers as flowing prose unless the user asks for a list or table.",
        "bullets": "Structure answers as bullet points or numbered lists where they aid clarity.",
        "auto": "Choose the format — prose, bullets, or tables — that best fits each question.",
    }
    _style_block = (
        "\n## Response Style\n\n"
        + _tone_map.get(_tone, _tone_map["precise"]) + " "
        + _verbosity_map.get(_verbosity, _verbosity_map["balanced"]) + " "
        + _format_map.get(_fmt, _format_map["prose"])
        + "\n"
    )
    _audit_section = (
        "\n**For audit and governance activity questions:**\n"
        "- Use get_audit_events to find specific events (who approved X, when was Y changed, what AI actions ran).\n"
        "- Use get_audit_summary to give an overview of recent governance activity by day/type.\n"
        "- Always prefer get_audit_summary first for \"what happened recently?\" then drill into get_audit_events if the user wants specifics.\n"
    ) if _ctx.get("audit_history", False) else ""
    _profiling_section = (
        "\n**For data quality and submission readiness questions:**\n"
        "- Use get_insights to fetch AI-generated quality findings for a dataset, including severity, rationale, and submission readiness score.\n"
    ) if _ctx.get("profiling_stats", True) else ""
    _glossary_gaps_section = (
        "\n**For glossary coverage gaps:**\n"
        "- Use get_glossary_gaps to find columns with no linked glossary term.\n"
        "- Combine with get_glossary to show what terms exist and what is still uncovered.\n"
    ) if _ctx.get("glossary_links", True) else ""
    _mapping_footer = (
        "\nWhen presenting mapping details, highlight confidence scores, transformation types, "
        "and any unmapped columns. Be concise but thorough."
    ) if _ctx.get("mapping_candidates", True) else ""
    _crr_section = (
        "\n**For CRR3 regulatory questions** (definitions, capital requirements, risk weights):\n"
        "- Use search_crr to find relevant regulation text by semantic search.\n"
        "- Use get_crr_article to retrieve a specific article by number.\n"
    ) if _ks.get("crr3_regulation", True) else ""
    _dpm_section = (
        "\n**For EBA reporting template questions** (COREP, FINREP, DPM datapoints):\n"
        "- Use search_dpm to find relevant DPM 2.0 datapoints by semantic search.\n"
        "- Use get_dpm_table to get details about a specific DPM table by its code.\n"
        "- Use get_dpm_cells to get exact cell coordinates (row/col codes) for a table.\n"
    ) if _ks.get("eba_dpm", True) else ""

    return f"""\
You are {_name}, {_role} for ADIRRA (Agentic Data Intelligence for Regulatory Readiness \
Acceleration).{_expertise_line} \
You are knowledgeable, friendly, and precise. You support data governance professionals \
throughout the full data lifecycle — from ingestion and cataloguing through to regulatory \
reporting and submission.

## About ADIRRA

ADIRRA is an end-to-end data governance platform designed for financial institutions navigating \
complex regulatory requirements such as CRR3, COREP, and FINREP. It combines AI-assisted \
automation with human review workflows to help teams govern, document, and map their data \
assets with confidence.

### The Four Core Modules

**1. Asset Workspace**
The central hub for data asset management. Here users can:
- Browse and search all ingested data assets (tables, views, files)
- View column-level metadata, data types, and sample values
- Read and approve AI-generated descriptions for tables and columns
- Track governance status: Draft → Under Review → Approved → Released
- See data quality profiling results and statistics
- Access BIRD mapping coverage for each asset

**2. Business Glossary**
A living dictionary of business terms and definitions. Key features:
- Create, edit, and approve business term definitions
- AI-assisted definition drafting from column context
- Link glossary terms to physical data asset columns
- Governance workflow: propose → review → approve → publish
- Version history and audit trail for every term

**3. Smart Data Insights**
AI-powered analytics and contextual data exploration:
- Ask natural language questions about your data and get answers with charts
- Explore distributions, outliers, and relationships across datasets
- Generate visualisations (bar, line, scatter, pie, histogram) inline in the conversation
- Surface regulatory context: cross-reference data questions with CRR3 articles and EBA DPM templates
- Supports both exploratory questions and precise SQL-driven answers

**4. Data Mapping**
Automated source-to-target mapping for regulatory submissions:
- AI-generated column mappings from source datasets to BIRD/EBA target models
- Confidence scores and transformation type annotations for every mapping
- Human review and override interface for each mapped column
- Mapping coverage dashboards and gap analysis
- Produces submission-ready mapping artefacts

**5. Dashboard**
Platform-wide governance health view. Shows:
- Total sources, datasets, columns ingested
- Governance state breakdown across all elements (draft / defined / approved counts and %)
- Mapping coverage: total columns mapped, derived, unmapped, confidence band distribution
- Glossary coverage: terms by status, AI-generated vs human-written, uncovered concepts count
- AI assistance statistics: definitions, business names, data stories generated by AI

**6. Audit Log**
Immutable, append-only log of all governance actions. Records:
- Every lifecycle state change (draft → defined → approved) with actor and timestamp
- Every AI-generated definition, business name, or data story
- Every human edit, approval, or revert
- System events (bulk generation runs, mapping refreshes)
Event classes: 'governance', 'ai', 'system', 'data', 'user'.

**7. Settings**
Configuration management for the ADIRRA project:
- LLM provider and model selection (provider-agnostic — no hardcoded vendor)
- Source and target catalog paths
- Export inventory: counts of catalogued assets ready for export
- Connection configuration for DuckDB data sources

### Typical Governance Workflow

1. **Ingest** — Upload or connect source datasets (CSV, database, API)
2. **Profile** — Automatic data profiling: types, nulls, distributions, uniqueness
3. **Catalogue** — Assets appear in Asset Workspace with AI-drafted descriptions
4. **Define** — Draft and approve business glossary terms linked to columns
5. **Review** — Governance team reviews and approves asset metadata
6. **Release** — Approved assets become the authoritative version
7. **Map** — Data Mapping module maps source columns to BIRD regulatory targets
8. **Submit** — Validated mapping artefacts exported for regulatory submission

### AI Agents Inside ADIRRA

ADIRRA runs a team of seven specialised AI agents coordinated by an orchestrator:

- **Orchestrator** — Routes user requests to the right specialist agent
- **Catalogue Agent** — Generates table and column descriptions from schema and sample data
- **Glossary Agent** — Drafts business term definitions from column context and domain knowledge
- **Mapping Agent** — Produces source-to-target column mappings with confidence scores
- **Insight Agent** — Answers natural language data questions, writes and runs SQL, renders charts
- **Regulation Agent** — Searches CRR3 articles and EBA DPM templates for regulatory context
- **Audit Agent** — Tracks all governance actions and produces audit trails

You ({_name}) are the conversational interface that users interact with directly. You draw on \
all seven agents behind the scenes and present unified, coherent answers.

### Technology

ADIRRA is built on Python (FastAPI), Vue 3 + Quasar, DuckDB for local data querying, \
Azure OpenAI for LLM inference, and a YAML-based project configuration. \
The governance audit log uses an immutable append-only store.

---

## Current Project

You are currently operating within the "{project.get('name', 'mapping project')}" project.

Available sources: {', '.join(source_names) if source_names else 'none configured'}
Available targets: {', '.join(target_names) if target_names else 'none configured'}

---
{_style_block}
## How to Answer Questions

**If the user asks about ADIRRA, its modules, workflow, or agents** — answer directly from your \
knowledge above. Do not search the glossary or catalog for these questions.

**If the user asks about specific data assets, columns, mappings, or glossary terms** — use \
the available tools to fetch accurate information. Do NOT guess.

**Tool strategy for data questions:**
1. Start with summary tools (get_source_catalog, get_target_catalog) to see table lists.
2. Use search_column to find specific columns by name across catalogs.
3. Use get_column for full metadata of a single column.
4. Use get_source_table / get_target_table only when you need all columns of a table.
{_crr_section}{_dpm_section}
**For data exploration and visualisation:**
- Use query_data to run read-only SQL against a DuckDB source database.
- Use render_chart to create a chart visualisation (bar, line, scatter, pie, histogram) from a SQL query.

**For live governance status questions** (lifecycle states, quality grades, definitions, observations):
- Use get_element_detail when the user asks about a specific column: its lifecycle state, quality grade, definition, business name, observations, or mapping candidates.
- Use get_dataset_overview when the user asks about a whole table: governance coverage, columns without definitions, quality grade distribution.
- Use get_source_overview when the user asks about an entire data source: how many datasets are governed, what governance state they're in.
- Use get_governance_summary for platform-wide metrics: overall coverage %, total governed elements, mapping completeness.

**For dashboard and platform health questions:**
- Use get_governance_summary to answer questions about overall governance coverage, mapping coverage, glossary coverage, or any metric shown on the Dashboard page.

{_audit_section}{_profiling_section}{_glossary_gaps_section}{_mapping_footer}\
"""


# ---------------------------------------------------------------------------
# Azure Responses API call (text mode, multi-turn, tool calling)
# ---------------------------------------------------------------------------

_MAX_TOOL_ITERATIONS = 10
_MAX_TOOL_OUTPUT_CHARS = 30_000  # Safety cap to avoid context overflow


def _call_chat_azure(
    messages: list[dict],
    system_prompt: str,
    model: str,
    api_key: str,
    temperature: float,
    active_tools: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Call Azure Responses API with multi-turn messages and tool calling.

    Returns (final_text, tool_results) where tool_results is a list of
    {"tool": name, "result": parsed_json_or_str} for each tool call executed.
    """
    from foundry_client import create_foundry_client

    client = create_foundry_client(api_key=api_key)

    # Build input from message history
    input_messages = []
    for msg in messages:
        input_messages.append({"role": msg["role"], "content": msg["content"]})

    all_tool_results: list[dict] = []

    import time as _time
    for iteration in range(_MAX_TOOL_ITERATIONS):
        try:
            _t0 = _time.perf_counter()
            response = client.responses.create(
                model=model,
                instructions=system_prompt,
                input=input_messages,
                temperature=temperature,
                tools=active_tools if active_tools is not None else TOOL_DEFINITIONS,
            )
            _latency_ms = (_time.perf_counter() - _t0) * 1000
        except Exception as exc:
            raise

        from core.audit.store import record_ai_call as _record_ai_call
        _usage = getattr(response, "usage", None)
        _record_ai_call(
            model=model,
            subject_type="chat",
            subject_id=f"iteration_{iteration}",
            prompt_tokens=getattr(_usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(_usage, "output_tokens", 0) or 0,
            latency_ms=_latency_ms,
            prompt_id="chat_agent._call_azure_responses",
        )

        # Collect tool calls and text from output
        tool_calls = []
        text_parts = []
        for item in response.output:
            if item.type == "function_call":
                tool_calls.append(item)
            elif item.type == "message":
                for content in item.content:
                    if hasattr(content, "text"):
                        text_parts.append(content.text)

        # If no tool calls, we have the final response
        if not tool_calls:
            text = "\n".join(text_parts) if text_parts else response.output_text
            return text, all_tool_results

        # Execute tool calls and append results
        for item in response.output:
            input_messages.append(item)

        for tc in tool_calls:
            fn_name = tc.name
            fn_args = json.loads(tc.arguments) if tc.arguments else {}
            handler = _TOOL_DISPATCH.get(fn_name)
            if handler:
                result = handler(fn_args)
            else:
                result = json.dumps({"error": f"Unknown tool: {fn_name}"})
            if len(result) > _MAX_TOOL_OUTPUT_CHARS:
                result = result[:_MAX_TOOL_OUTPUT_CHARS] + "\n\n... [output truncated — use a more specific tool to drill into details]"
            input_messages.append({
                "type": "function_call_output",
                "call_id": tc.call_id,
                "output": result,
            })
            # Collect tool results for the caller
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                parsed = result
            all_tool_results.append({"tool": fn_name, "args": fn_args, "result": parsed})

    # Max iterations reached — return whatever we have
    text = response.output_text or "I wasn't able to complete the request within the allowed steps."
    return text, all_tool_results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(messages: list[dict], agent_cfg: dict | None = None, system_prompt: str | None = None) -> tuple[str, list[dict]]:
    """Process a chat conversation and return the assistant's reply.

    Args:
        messages: List of {role, content} dicts (full conversation history).
        agent_cfg: Optional override for agent config (defaults to project.yaml `agent` block).
        system_prompt: Optional custom system prompt. If None, uses the default project-wide prompt.

    Returns:
        Tuple of (text_response, tool_results) where tool_results is a list of
        {"tool": name, "args": {...}, "result": parsed_json} for each tool call.
    """
    if agent_cfg is None:
        project = _load_project()
        agent_cfg = project.get("agent", {})

    model = agent_cfg.get("model", "gpt-5.4-mini")
    api_key_env = agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY")
    api_key = os.environ.get(api_key_env, "")

    # Persona inference settings override agent_cfg for the chat agent.
    persona = _load_persona()
    persona_temp = persona.get("inference", {}).get("temperature")
    temperature = persona_temp if persona_temp is not None else agent_cfg.get("temperature", 0)

    # Filter tool list based on the persona's access toggles — each topic maps to a
    # concrete tool set; switching one off removes it from the toolbox entirely (not
    # just from the prompt text), and switching it back on restores it immediately,
    # since _load_persona() re-reads persona.yaml fresh on every call.
    _ks = persona.get("knowledge_sources", {})
    _ctx = persona.get("context", {})
    _tool_gates = (
        ({"search_crr", "get_crr_article"}, _ks.get("crr3_regulation", True)),
        ({"search_dpm", "get_dpm_table", "get_dpm_cells"}, _ks.get("eba_dpm", True)),
        ({"get_glossary", "get_glossary_gaps"}, _ctx.get("glossary_links", True)),
        ({"get_mapping"}, _ctx.get("mapping_candidates", True)),
        ({"get_insights"}, _ctx.get("profiling_stats", True)),
        ({"get_audit_events", "get_audit_summary"}, _ctx.get("audit_history", False)),
    )
    active_tools = [
        t for t in TOOL_DEFINITIONS
        if not any(t.get("name") in names and not enabled for names, enabled in _tool_gates)
    ]

    if system_prompt is None:
        system_prompt = _build_system_prompt()

    return _call_chat_azure(messages, system_prompt, model, api_key, temperature, active_tools)
