"""
catalog_builder.py  –  Build unified catalog YAMLs per source/target.

Reads project.yaml to discover sources and targets. For each entry:
  - Loads or extracts a schema (via the extractors module).
  - Optionally enriches with per-column statistics.
  - Writes a single catalog YAML file.

Usage:
    python catalog_builder.py                  # all sources + targets in project.yaml
    python catalog_builder.py --name banking   # one entry only

Output:
    sources/<name>.yaml   (for sources)
    targets/<name>.yaml   (for targets)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from connectors import load_connector
from core.extractors import load_schema_yaml, extract_schema_from_db, enrich_schemas
from core.yaml_cache import load_yaml_cached
from core.catalog import save_catalog_dispatch

PROJECT_FILE = _ROOT / "project.yaml"

# ---------------------------------------------------------------------------
# Project loading
# ---------------------------------------------------------------------------

def load_project() -> dict:
    return load_yaml_cached(PROJECT_FILE)


def _find_connection(name: str, project: dict) -> dict:
    connections_file = _ROOT / project.get("connections_file", "connections.yaml")
    with connections_file.open(encoding="utf-8") as fh:
        connections = yaml.safe_load(fh)["connections"]
    for cfg in connections:
        if cfg["name"] == name:
            cfg["_root"] = str(_ROOT)  # allow connectors to resolve relative paths
            return cfg
    raise ValueError(f"Connection '{name}' not found in {connections_file}.")


# ---------------------------------------------------------------------------
# Schema hash
# ---------------------------------------------------------------------------

def _compute_schema_hash(schemas: list[dict]) -> str:
    """Stable hash of all (schema.table.column, data_type) pairs."""
    entries = sorted(
        f"{s['name']}.{t.get('table_name', t.get('name'))}.{c['name']}:{c['data_type']}"
        for s in schemas
        for t in s.get("tables", [])
        for c in t.get("columns", [])
    )
    return hashlib.md5(json.dumps(entries).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Build & write catalog
# ---------------------------------------------------------------------------

def _flatten_columns(source_name: str, schemas: list[dict]) -> list[dict]:
    """Flat list of every ColumnProfile for agent-friendly lookup."""
    rows: list[dict] = []
    for schema in schemas:
        for table in schema.get("tables", []):
            for col in table.get("columns", []):
                row: dict = {
                    "source": source_name,
                    "schema": table.get("schema_name", schema["name"]),
                    "table": table.get("table_name", table.get("name")),
                    "table_description": table.get("description"),
                    **col,
                }
                rows.append(row)
    return rows


def _schema_to_profile_tables(schemas: list[dict]) -> list[dict]:
    """Convert raw schema tables (no stats) to TableInfo-shaped dicts."""
    result = []
    for schema in schemas:
        tables = []
        for tbl in schema.get("tables", []):
            cols = [
                {
                    "name": c.get("name"),
                    "description": c.get("description"),
                    "data_type": c.get("data_type"),
                    "row_count": None,
                    "null_count": None,
                    "null_pct": None,
                    "distinct_count": None,
                    "min_value": None,
                    "max_value": None,
                    "sample_values": [],
                }
                for c in tbl.get("columns", [])
            ]
            tables.append({
                "schema_name": schema["name"],
                "table_name": tbl.get("name"),
                "description": tbl.get("description"),
                "row_count": None,
                "primary_key": [],
                "foreign_keys": [],
                "relations": [],
                "columns": cols,
            })
        result.append({**schema, "tables": tables})
    return result


def build_catalog(source_cfg: dict, project: dict) -> dict:
    conn_name = source_cfg.get("connection")
    conn_cfg = _find_connection(conn_name, project) if conn_name else {}

    # type: yaml — catalog is provided as-is from an external YAML file
    if conn_cfg.get("type") == "yaml":
        yaml_path = Path(conn_cfg["file"])
        if not yaml_path.is_absolute():
            yaml_path = _ROOT / yaml_path
        print(f"  Loading pre-built catalog from '{yaml_path}' ...")
        with yaml_path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    schema_file = source_cfg.get("schema_file")
    if schema_file:
        schema_data = load_schema_yaml(schema_file)
    else:
        print(f"  Extracting schema via '{conn_cfg['name']}' ...")
        schema_data = extract_schema_from_db(conn_cfg)
    schemas = schema_data.get("schemas", [])
    schema_only = source_cfg.get("schema_only", False)

    # Excel connector is metadata-only — always schema_only
    if conn_cfg.get("type") == "schema_excel":
        schema_only = True

    if schema_only:
        print("  Schema only — using schema metadata without stats.")
        enriched_schemas = _schema_to_profile_tables(schemas)
        # For connectors that have constraints (e.g. Excel), enrich with PK/FK/relations
        if conn_cfg.get("type") in ("schema_excel",):
            with load_connector(conn_cfg) as conn:
                for schema in enriched_schemas:
                    constraints = conn.fetch_constraints(schema["name"])
                    for tbl in schema.get("tables", []):
                        tbl_name = tbl.get("table_name", tbl.get("name"))
                        c = constraints.get(tbl_name, {})
                        tbl["primary_key"] = c.get("primary_key", [])
                        tbl["foreign_keys"] = c.get("foreign_keys", [])
                        tbl["relations"] = c.get("relations", [])
    else:
        print(f"  Enriching with stats via '{conn_cfg['name']}' ...")
        with load_connector(conn_cfg) as conn:
            enriched_schemas = enrich_schemas(conn, schemas)

    return {
        "version": 2,
        "source": source_cfg["name"],
        "connection": source_cfg.get("connection"),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "schema_hash": _compute_schema_hash(enriched_schemas),
        "schemas": enriched_schemas,
        "columns": _flatten_columns(source_cfg["name"], enriched_schemas),
    }


def _to_yaml_safe(value):
    """Convert profiler output to plain YAML-safe Python types."""
    if isinstance(value, dict):
        return {key: _to_yaml_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_yaml_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_yaml_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def save_catalog(source_name: str, catalog: dict, catalogs_dir: Path, *, kind: str = "source") -> Path:
    """Respects catalog_backend (Phase 6): postgres writes go through core.catalog_db.save_catalog;
    yaml writes are unchanged (same sanitization, same file layout)."""
    out_path = catalogs_dir / f"{source_name}.yaml"
    save_catalog_dispatch(out_path, _to_yaml_safe(catalog), kind=kind)
    return out_path


# ---------------------------------------------------------------------------
# Auto-build on startup
# ---------------------------------------------------------------------------

def _get_current_schema_hash(source_cfg: dict, project: dict) -> str | None:
    """Compute schema hash from current source without full enrichment."""
    conn_name = source_cfg.get("connection")
    if not conn_name:
        return None
    conn_cfg = _find_connection(conn_name, project)

    if conn_cfg.get("type") == "yaml":
        yaml_path = Path(conn_cfg["file"])
        if not yaml_path.is_absolute():
            yaml_path = _ROOT / yaml_path
        with yaml_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("schema_hash")

    schema_file = source_cfg.get("schema_file")
    if schema_file:
        schema_data = load_schema_yaml(schema_file)
    else:
        schema_data = extract_schema_from_db(conn_cfg)

    schemas = schema_data.get("schemas", [])
    return _compute_schema_hash(schemas)


def ensure_catalogs(project: dict | None = None) -> list[str]:
    """Build catalogs that are missing or whose schema hash has changed.

    Returns list of catalog names that were (re)built.
    """
    if project is None:
        project = load_project()

    paths = project.get("paths", {})
    source_dir = _ROOT / paths.get("source_catalogs", "sources")
    target_dir = _ROOT / paths.get("target_catalogs", "targets")

    entries = [
        (e, source_dir, "source") for e in project.get("sources", [])
    ] + [
        (e, target_dir, "target") for e in project.get("targets", [])
    ]

    rebuilt = []
    for entry_cfg, catalogs_dir, kind in entries:
        name = entry_cfg["name"]
        catalog_path = catalogs_dir / f"{name}.yaml"

        # Read existing hash
        existing_hash = None
        if catalog_path.exists():
            with catalog_path.open(encoding="utf-8") as fh:
                existing = yaml.safe_load(fh)
            existing_hash = existing.get("schema_hash") if existing else None

        # Compute current hash
        try:
            current_hash = _get_current_schema_hash(entry_cfg, project)
        except Exception as exc:
            print(f"  Warning: could not check schema for '{name}': {exc}")
            continue

        if existing_hash and existing_hash == current_hash:
            continue

        # Build and save
        reason = "new" if not existing_hash else "schema changed"
        print(f"  Building catalog: {name} ({reason})")
        try:
            catalog = build_catalog(entry_cfg, project)
            save_catalog(name, catalog, catalogs_dir, kind=kind)
            n_tables = sum(len(s["tables"]) for s in catalog["schemas"])
            print(f"    -> {name}.yaml ({n_tables} tables)")
            rebuilt.append(name)
        except Exception as exc:
            print(f"  ERROR building '{name}': {exc}")

    return rebuilt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build unified catalog YAML files from schema + database stats."
    )
    parser.add_argument("--name", default=None, help="Process only this source/target name (default: all)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = load_project()
    paths = project.get("paths", {})
    source_catalogs_dir = _ROOT / paths.get("source_catalogs", paths.get("catalogs", "sources"))
    target_catalogs_dir = _ROOT / paths.get("target_catalogs", paths.get("catalogs", "targets"))

    # Process both sources and targets — agents need catalogs for both sides
    sources = [(e, source_catalogs_dir, "source") for e in project.get("sources", [])]
    targets_list = [(e, target_catalogs_dir, "target") for e in project.get("targets", [])]
    all_entries = sources + targets_list
    if args.name:
        all_entries = [(e, d, k) for e, d, k in all_entries if e["name"] == args.name]
        if not all_entries:
            raise SystemExit(f"'{args.name}' not found in project.yaml sources or targets.")

    for entry_cfg, catalogs_dir, kind in all_entries:
        name = entry_cfg["name"]
        print(f"\nBuilding catalog: {name}")
        try:
            catalog = build_catalog(entry_cfg, project)
            path = save_catalog(name, catalog, catalogs_dir, kind=kind)
            n_tables = sum(len(s["tables"]) for s in catalog["schemas"])
            print(f"  -> {path}  ({n_tables} tables, hash: {catalog['schema_hash'][:8]}...)")
        except Exception as exc:
            print(f"  ERROR: {exc}")


if __name__ == "__main__":
    main()
