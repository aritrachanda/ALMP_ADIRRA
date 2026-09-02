"""
crdm_to_yaml.py  –  Extract mappings/target_catalogs/crdm.yaml from sources/duckdb/crdm.duckdb.

The crdm.duckdb is a metadata database containing three tables:
  - crdm.tables    (table_name, description, column_count, pk_columns)
  - crdm.columns   (table_name, column_name, data_type, description, is_pk, is_fk, …)
  - crdm.dependencies  (currently empty)

Table names are fully qualified like "CRDM.input.TableName".
We split into schema = "CRDM.input" (or whatever prefix) and table = "TableName".

Usage:
    python sources/loader/crdm_to_yaml.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb
import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = Path(__file__).resolve().parent.parent / "duckdb" / "crdm.duckdb"
OUTPUT = _ROOT / "mappings" / "target_catalogs" / "crdm.yaml"

SOURCE_NAME = "crdm"


def _split_table_name(fq_name: str) -> tuple[str, str]:
    """Split 'CRDM.input.TableName' → ('CRDM.input', 'TableName')."""
    parts = fq_name.rsplit(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]


def _compute_schema_hash(schemas: list[dict]) -> str:
    entries = sorted(
        f"{s['name']}.{t['table_name']}.{c['name']}:{c['data_type']}"
        for s in schemas
        for t in s.get("tables", [])
        for c in t.get("columns", [])
    )
    return hashlib.md5(json.dumps(entries).encode()).hexdigest()


def extract() -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True)

    # Load tables metadata
    tables_rows = con.execute(
        "SELECT table_name, description, pk_columns FROM crdm.crdm.tables"
    ).fetchall()
    table_meta = {}
    for fq_name, desc, pk_cols in tables_rows:
        pk_list = [c.strip() for c in (pk_cols or "").split(",") if c.strip()]
        table_meta[fq_name] = {"description": desc or "", "pk_columns": pk_list}

    # Load columns metadata
    col_rows = con.execute(
        "SELECT table_name, column_name, data_type, description, is_pk, is_fk "
        "FROM crdm.crdm.columns ORDER BY table_name, column_name"
    ).fetchall()

    # Group columns by fully-qualified table name
    table_columns: dict[str, list[dict]] = defaultdict(list)
    for fq_table, col_name, dtype, desc, is_pk, is_fk in col_rows:
        table_columns[fq_table].append({
            "name": col_name,
            "description": desc or "",
            "data_type": dtype or "VARCHAR",
            "is_pk": bool(is_pk),
            "is_fk": bool(is_fk),
        })

    con.close()

    # Build schema-grouped structure
    schema_tables: dict[str, list[dict]] = defaultdict(list)
    for fq_table in sorted(table_columns.keys()):
        schema_name, table_name = _split_table_name(fq_table)
        meta = table_meta.get(fq_table, {"description": "", "pk_columns": []})
        cols = table_columns[fq_table]

        pk_cols = meta["pk_columns"] or [c["name"] for c in cols if c["is_pk"]]

        columns_out = [
            {
                "name": c["name"],
                "description": c["description"],
                "data_type": c["data_type"],
                "row_count": None,
                "null_count": None,
                "null_pct": None,
                "distinct_count": None,
                "min_value": None,
                "max_value": None,
                "sample_values": [],
            }
            for c in cols
        ]

        schema_tables[schema_name].append({
            "schema_name": schema_name,
            "table_name": table_name,
            "description": meta["description"],
            "row_count": None,
            "primary_key": pk_cols,
            "foreign_keys": [],
            "relations": [],
            "columns": columns_out,
        })

    schemas = [
        {"name": schema_name, "tables": tables}
        for schema_name, tables in sorted(schema_tables.items())
    ]

    # Flat column list for agent lookup
    flat_columns = []
    for schema in schemas:
        for table in schema["tables"]:
            for col in table["columns"]:
                flat_columns.append({
                    "source": SOURCE_NAME,
                    "schema": table["schema_name"],
                    "table": table["table_name"],
                    "table_description": table.get("description"),
                    **col,
                })

    return {
        "version": 2,
        "source": SOURCE_NAME,
        "connection": SOURCE_NAME,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "schema_hash": _compute_schema_hash(schemas),
        "schemas": schemas,
        "columns": flat_columns,
    }


def main():
    print(f"Reading {DB_PATH} ...")
    catalog = extract()
    n_schemas = len(catalog["schemas"])
    n_tables = sum(len(s["tables"]) for s in catalog["schemas"])
    n_cols = len(catalog["columns"])
    print(f"  Found {n_schemas} schema(s), {n_tables} table(s), {n_cols} column(s)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        yaml.dump(catalog, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  Written to {OUTPUT}")


if __name__ == "__main__":
    main()
