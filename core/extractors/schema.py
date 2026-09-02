"""
extractors.schema  –  Schema extraction from databases and YAML files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "core"))

from connectors import load_connector


def load_schema_yaml(schema_file: str) -> dict:
    """Load a pre-built schema YAML file (relative to project root)."""
    path = _ROOT / schema_file
    if not path.exists():
        raise FileNotFoundError(
            f"Schema file '{path}' not found. "
            "Run the source ingestion script first (e.g. bird_to_yaml.py)."
        )
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def extract_schema_from_db(conn_cfg: dict) -> dict:
    """Extract schema via information_schema (respects 'schemas' filter in conn config)."""
    schemas_filter = conn_cfg.get("schemas")
    with load_connector(conn_cfg) as conn:
        schemas = conn.get_schemas()
        comments = conn.fetch_comments(schemas_filter)

    # Merge comments into schema structure
    if comments:
        for schema in schemas:
            schema_comments = comments.get(schema["name"], {})
            for table in schema.get("tables", []):
                table_name = table.get("name", "")
                table_comments = schema_comments.get(table_name, {})
                if table_comments.get("comment") and not table.get("description"):
                    table["description"] = table_comments["comment"]
                col_comments = table_comments.get("columns", {})
                for col in table.get("columns", []):
                    col_comment = col_comments.get(col["name"])
                    if col_comment and not col.get("description"):
                        col["description"] = col_comment

    return {
        "version": 2,
        "connection": conn_cfg["name"],
        "type": conn_cfg["type"],
        "schemas": schemas,
    }
