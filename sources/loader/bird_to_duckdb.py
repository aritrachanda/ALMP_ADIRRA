"""
bird_to_duckdb.py  –  Convert the BIRD Excel data model to a normalized DuckDB store.

Reads `sources/original/BIRD_data_model_rdbms.xlsx` (sheets: `schemas`, `relations`)
and writes `sources/duckdb/bird.duckdb` with three tables under the `bird` schema:

    bird.entities    (schema_name, table_name, framework, layer, description)
    bird.attributes  (schema_name, table_name, column_name, data_type,
                      is_pk, is_fk, role, description, codification, mandatory)
    bird.relations   (table, key, reference_table, reference_key)

Framework / role / codification are populated when determinable from the Excel,
otherwise sensible defaults are used (`layer='IL'`, `role='Attribute'`).

Usage:
    python sources/loader/bird_to_duckdb.py
    python sources/loader/bird_to_yaml.py --input sources/original/BIRD_data_model_rdbms.xlsx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

_HERE = Path(__file__).resolve().parent
_DEFAULT_INPUT = _HERE.parent / "original" / "BIRD_data_model_rdbms.xlsx"
_DEFAULT_OUTPUT = _HERE.parent / "duckdb" / "bird.duckdb"

# Excel data type → SQL-like type used in catalogs (matches SchemaExcelConnector).
_TYPE_MAP = {
    "string": "VARCHAR",
    "date": "DATE",
    "number": "DOUBLE",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
}


def _normalize_type(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "VARCHAR"
    base = str(raw).strip().lower().split("(")[0]
    return _TYPE_MAP.get(base, "VARCHAR")


def _bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "y")


def _strip_label_prefix(text) -> str:
    """Strip 'Label: description' → 'description' to match Excel description style."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text)
    if ": " in s:
        return s.split(": ", 1)[1]
    return s


def _opt_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s or None


def load_schemas_sheet(xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name="schemas")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_relations_sheet(xlsx: Path) -> pd.DataFrame:
    try:
        df = pd.read_excel(xlsx, sheet_name="relations")
    except ValueError:
        df = pd.DataFrame(columns=["table", "reference table", "key", "reference key"])
    df.columns = [str(c).strip() for c in df.columns]
    return df


def build_entities(schemas_df: pd.DataFrame) -> list[tuple]:
    """One row per (schema, table). Pulls description, framework, layer when present."""
    rows: list[tuple] = []
    seen: set[tuple[str, str]] = set()

    has_framework = "framework" in schemas_df.columns
    has_layer = "layer" in schemas_df.columns

    for (schema, table), group in schemas_df.groupby(["schema", "table"], sort=False):
        key = (str(schema), str(table))
        if key in seen:
            continue
        seen.add(key)

        desc = group["table description"].iloc[0] if "table description" in group.columns else None
        framework = _opt_str(group["framework"].iloc[0]) if has_framework else None
        layer = _opt_str(group["layer"].iloc[0]) if has_layer else None
        rows.append((
            str(schema),
            str(table),
            framework,
            layer or "IL",
            _opt_str(desc),
        ))
    return rows


def build_attributes(schemas_df: pd.DataFrame) -> list[tuple]:
    """One row per (schema, table, column)."""
    rows: list[tuple] = []
    has_role = "role" in schemas_df.columns
    has_codification = "codification" in schemas_df.columns

    for _, r in schemas_df.iterrows():
        rows.append((
            str(r["schema"]),
            str(r["table"]),
            str(r["column"]),
            _normalize_type(r.get("data type")),
            _bool(r.get("primary key")),
            _bool(r.get("foreign key")),
            (_opt_str(r["role"]) if has_role else None) or "Attribute",
            _strip_label_prefix(r.get("column description", "")) or None,
            _opt_str(r["codification"]) if has_codification else None,
            _bool(r.get("is mandatory")),
        ))
    return rows


def build_relations(relations_df: pd.DataFrame) -> list[tuple]:
    rows: list[tuple] = []
    if relations_df.empty:
        return rows
    for _, r in relations_df.iterrows():
        rows.append((
            _opt_str(r.get("table")),
            _opt_str(r.get("key")),
            _opt_str(r.get("reference table")),
            _opt_str(r.get("reference key")),
        ))
    return rows


_DDL = """
DROP SCHEMA IF EXISTS meta CASCADE;
CREATE SCHEMA meta;

CREATE TABLE meta.entities (
    schema_name  VARCHAR,
    table_name   VARCHAR,
    framework    VARCHAR,
    layer        VARCHAR,
    description  VARCHAR,
    PRIMARY KEY (schema_name, table_name)
);

CREATE TABLE meta.attributes (
    schema_name  VARCHAR,
    table_name   VARCHAR,
    column_name  VARCHAR,
    data_type    VARCHAR,
    is_pk        BOOLEAN,
    is_fk        BOOLEAN,
    role         VARCHAR,
    description  VARCHAR,
    codification VARCHAR,
    mandatory    BOOLEAN,
    PRIMARY KEY (schema_name, table_name, column_name)
);

CREATE TABLE meta.relations (
    table_name        VARCHAR,
    key               VARCHAR,
    reference_table   VARCHAR,
    reference_key     VARCHAR
);
"""


def write_duckdb(out_path: Path,
                 entities: list[tuple],
                 attributes: list[tuple],
                 relations: list[tuple]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    con = duckdb.connect(str(out_path))
    try:
        con.execute(_DDL)
        if entities:
            con.executemany(
                "INSERT INTO meta.entities VALUES (?, ?, ?, ?, ?)",
                entities,
            )
        if attributes:
            con.executemany(
                "INSERT INTO meta.attributes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                attributes,
            )
        if relations:
            con.executemany(
                "INSERT INTO meta.relations VALUES (?, ?, ?, ?)",
                relations,
            )
        con.commit()
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(_DEFAULT_INPUT),
                        help="Path to BIRD_data_model_rdbms.xlsx")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT),
                        help="Output DuckDB path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xlsx = Path(args.input)
    out_path = Path(args.output)

    print(f"Input  : {xlsx}")
    print(f"Output : {out_path}")

    schemas_df = load_schemas_sheet(xlsx)
    relations_df = load_relations_sheet(xlsx)

    entities = build_entities(schemas_df)
    attributes = build_attributes(schemas_df)
    relations = build_relations(relations_df)

    print(f"  Entities   : {len(entities)}")
    print(f"  Attributes : {len(attributes)}")
    print(f"  Relations  : {len(relations)}")

    write_duckdb(out_path, entities, attributes, relations)
    print("Done.")


if __name__ == "__main__":
    main()
