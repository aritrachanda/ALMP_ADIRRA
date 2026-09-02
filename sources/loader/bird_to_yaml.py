"""
bird_to_yaml.py  –  Extract `mappings/target_catalogs/bird.yaml` from `sources/duckdb/bird.duckdb`.

Reads the normalized BIRD metadata store produced by `bird_to_duckdb.py` and
writes a catalog YAML that is compatible with the existing `yaml`-typed
connection in `connections.yaml`.

The output mirrors the catalog shape produced by `core/catalog_builder.py`,
extended with BIRD-specific per-column metadata: `framework`, `role`,
`codification`, `mandatory`.

Usage:
    python sources/loader/bird_to_yaml.py
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb
import yaml

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_DEFAULT_DB = _HERE.parent / "duckdb" / "bird.duckdb"
_DEFAULT_OUTPUT = _ROOT / "mappings" / "target_catalogs" / "bird.yaml"

SOURCE_NAME = "bird"


def _compute_schema_hash(schemas: list[dict]) -> str:
    entries = sorted(
        f"{s['name']}.{t['table_name']}.{c['name']}:{c['data_type']}"
        for s in schemas
        for t in s.get("tables", [])
        for c in t.get("columns", [])
    )
    return hashlib.md5(json.dumps(entries).encode()).hexdigest()


def extract(db_path: Path) -> dict:
    con = duckdb.connect(str(db_path), read_only=True)

    entity_rows = con.execute(
        "SELECT schema_name, table_name, framework, layer, description "
        "FROM meta.entities ORDER BY schema_name, table_name"
    ).fetchall()

    attr_rows = con.execute(
        "SELECT schema_name, table_name, column_name, data_type, "
        "is_pk, is_fk, role, description, codification, mandatory "
        "FROM meta.attributes ORDER BY schema_name, table_name, column_name"
    ).fetchall()

    relation_rows = con.execute(
        "SELECT table_name, key, reference_table, reference_key "
        "FROM meta.relations"
    ).fetchall()
    con.close()

    # Index entities and group columns by table.
    entity_meta: dict[tuple[str, str], dict] = {}
    for schema, table, framework, layer, desc in entity_rows:
        entity_meta[(schema, table)] = {
            "framework": framework,
            "layer": layer,
            "description": desc,
        }

    table_columns: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (schema, table, col, dtype, is_pk, is_fk, role,
         desc, codification, mandatory) in attr_rows:
        table_columns[(schema, table)].append({
            "name": col,
            "description": desc,
            "data_type": dtype or "VARCHAR",
            "row_count": None,
            "null_count": None,
            "null_pct": None,
            "distinct_count": None,
            "min_value": None,
            "max_value": None,
            "sample_values": [],
            # BIRD extras
            "framework": entity_meta.get((schema, table), {}).get("framework"),
            "role": role or "Attribute",
            "codification": codification,
            "mandatory": bool(mandatory),
            "is_pk": bool(is_pk),
            "is_fk": bool(is_fk),
        })

    # Build relations index keyed by child table (the FK side).
    # bird.relations matches the Excel `relations` sheet semantics where
    # `table` is the parent (PK side) and `reference table` is the child (FK side).
    relations_by_child: dict[str, list[dict]] = defaultdict(list)
    for parent_table, key, child_table, ref_key in relation_rows:
        if not child_table or not parent_table:
            continue
        relations_by_child[child_table].append({
            "reference_table": parent_table,
            "columns": [ref_key] if ref_key else [],
            "reference_table_columns": [key] if key else [],
        })

    # Group tables by schema.
    schema_tables: dict[str, list[dict]] = defaultdict(list)
    for (schema, table), cols in table_columns.items():
        meta = entity_meta.get((schema, table), {})
        pk_cols = [c["name"] for c in cols if c["is_pk"]]
        fk_cols = [c["name"] for c in cols if c["is_fk"]]
        schema_tables[schema].append({
            "schema_name": schema,
            "table_name": table,
            "description": meta.get("description"),
            "framework": meta.get("framework"),
            "layer": meta.get("layer") or "IL",
            "row_count": None,
            "primary_key": pk_cols,
            "foreign_keys": fk_cols,
            "relations": relations_by_child.get(table, []),
            "columns": cols,
        })

    schemas = [
        {"name": s_name, "tables": tables}
        for s_name, tables in sorted(schema_tables.items())
    ]

    flat_columns: list[dict] = []
    for schema in schemas:
        for table in schema["tables"]:
            for col in table["columns"]:
                flat_columns.append({
                    "source": SOURCE_NAME,
                    "schema": table["schema_name"],
                    "table": table["table_name"],
                    "table_description": table.get("description"),
                    "framework": table.get("framework"),
                    "layer": table.get("layer"),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(_DEFAULT_DB),
                        help="Path to bird.duckdb")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT),
                        help="Output YAML path (default: mappings/target_catalogs/bird.yaml)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_path = Path(args.output)

    print(f"Reading {db_path} ...")
    catalog = extract(db_path)
    n_schemas = len(catalog["schemas"])
    n_tables = sum(len(s["tables"]) for s in catalog["schemas"])
    n_cols = len(catalog["columns"])
    print(f"  {n_schemas} schema(s), {n_tables} table(s), {n_cols} column(s)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.dump(catalog, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  Written to {out_path}")


if __name__ == "__main__":
    main()
