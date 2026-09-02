"""
connectors.py  –  Database connector abstractions.

Supported backends: duckdb
"""
from __future__ import annotations

import abc
import os
from pathlib import Path
from typing import Any


class BaseConnector(abc.ABC):
    """Abstract base for all database connectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name: str = config["name"]
        self._conn: Any = None

    @abc.abstractmethod
    def connect(self) -> None:
        """Open the database connection."""

    @abc.abstractmethod
    def execute(self, query: str, params: tuple = ()) -> list[tuple]:
        """Execute *query* and return all result rows."""

    def close(self) -> None:
        """Close the connection if it is open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "BaseConnector":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def get_schemas(self) -> list[dict]:
        """Return the schema tree: list of schemas → tables → columns.

        If config['schemas'] is set (a list of schema names), only those schemas
        are extracted. Otherwise all non-system schemas are returned.
        """
        schemas_filter = self.config.get("schemas")
        rows = self._fetch_schema_rows(schemas_filter)
        return _build_schema_structure(rows)

    def fetch_constraints(self, schema_name: str) -> dict[str, dict]:
        """Return constraints for all tables in *schema_name*.

        Returns a dict keyed by table_name:
            {
                "primary_key": [col, ...],
                "foreign_keys": [col, ...],
                "relations": [
                    {"reference_table": "...", "columns": [...], "reference_table_columns": [...]}
                ]
            }

        - foreign_keys: flat list of column names that are foreign keys
        - relations: detailed relationship info (which table/columns they reference)

        Subclasses should override this with database-specific logic.
        The default implementation returns an empty dict (no constraints).
        """
        return {}

    def fetch_comments(self, schemas_filter: list[str] | None = None) -> dict[str, dict]:
        """Return table/column comments from the database.

        Returns a dict keyed by schema_name:
            {
                schema_name: {
                    table_name: {
                        "comment": "table comment" | None,
                        "columns": {col_name: "column comment", ...}
                    }
                }
            }

        Subclasses should override this with database-specific logic.
        The default implementation returns an empty dict (no comments).
        """
        return {}

    @abc.abstractmethod
    def _fetch_schema_rows(self, schemas_filter: list[str] | None = None) -> list[tuple]:
        """
        Return rows of:
            (schema_name, table_name, column_name, data_type, is_nullable, column_default)
        ordered by schema / table / ordinal position.

        If schemas_filter is provided, only return rows for those schemas.
        """


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _build_schema_structure(rows: list[tuple]) -> list[dict]:
    schemas: dict[str, dict[str, list]] = {}
    for schema_name, table_name, col_name, data_type, is_nullable, col_default in rows:
        schemas.setdefault(schema_name, {}).setdefault(table_name, []).append({
            "name": col_name,
            "data_type": data_type,
            "nullable": is_nullable.upper() == "YES",
            "default": col_default,
        })
    return [
        {
            "name": schema_name,
            "tables": [{"name": tbl, "columns": cols} for tbl, cols in tables.items()],
        }
        for schema_name, tables in schemas.items()
    ]


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------

class DuckDBConnector(BaseConnector):
    """Connector for local DuckDB databases."""

    def connect(self) -> None:
        import duckdb
        db_path = self.config.get("database", ":memory:")
        read_only = bool(self.config.get("read_only", False))
        if db_path != ":memory:" and not read_only:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path), read_only=read_only)

    def execute(self, query: str, params: tuple = ()) -> list[tuple]:
        return self._conn.execute(query, list(params)).fetchall()

    def _fetch_schema_rows(self, schemas_filter: list[str] | None = None) -> list[tuple]:
        where = ["t.table_type = 'BASE TABLE'", "c.table_schema NOT IN ('information_schema', 'pg_catalog')"]
        params: list = []
        if schemas_filter:
            placeholders = ", ".join("?" for _ in schemas_filter)
            where.append(f"c.table_schema IN ({placeholders})")
            params.extend(schemas_filter)
        where_clause = " AND ".join(where)
        return self.execute(f"""
            SELECT
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            JOIN information_schema.tables t
                ON  c.table_schema = t.table_schema
                AND c.table_name   = t.table_name
            WHERE {where_clause}
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """, tuple(params))

    def fetch_constraints(self, schema_name: str) -> dict[str, dict]:
        import re
        fk_re = re.compile(
            r"FOREIGN KEY\s*\((?P<cols>[^)]+)\)\s+REFERENCES\s+(?P<ref>[^\s(]+)\((?P<ref_cols>[^)]+)\)",
            re.IGNORECASE,
        )
        try:
            rows = self.execute(
                "SELECT table_name, constraint_type, constraint_column_names, constraint_text "
                "FROM duckdb_constraints() "
                "WHERE schema_name = ? AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')",
                (schema_name,),
            )
        except Exception:
            return {}

        result: dict[str, dict] = {}
        for table_name, ctype, col_names, ctext in rows:
            entry = result.setdefault(table_name, {"primary_key": [], "foreign_keys": [], "relations": []})
            if ctype == "PRIMARY KEY":
                entry["primary_key"] = list(col_names)
            elif ctype == "FOREIGN KEY":
                m = fk_re.search(ctext or "")
                if m:
                    ref_parts = m.group("ref").split(".")
                    ref_table = ref_parts[-1]
                    fk_cols = [c.strip() for c in m.group("cols").split(",")]
                    ref_cols = [c.strip() for c in m.group("ref_cols").split(",")]
                    # Add column names to foreign_keys flat list
                    for c in fk_cols:
                        if c not in entry["foreign_keys"]:
                            entry["foreign_keys"].append(c)
                    # Add detailed relation
                    entry["relations"].append({
                        "reference_table": ref_table,
                        "columns": fk_cols,
                        "reference_table_columns": ref_cols,
                    })
        return result

    def fetch_comments(self, schemas_filter: list[str] | None = None) -> dict[str, dict]:
        result: dict[str, dict] = {}
        try:
            where = ["NOT internal", "schema_name NOT IN ('information_schema', 'pg_catalog')"]
            params: list = []
            if schemas_filter:
                placeholders = ", ".join("?" for _ in schemas_filter)
                where.append(f"schema_name IN ({placeholders})")
                params.extend(schemas_filter)
            where_clause = " AND ".join(where)

            # Table comments
            table_rows = self.execute(
                f"SELECT schema_name, table_name, comment FROM duckdb_tables() WHERE {where_clause}",
                tuple(params),
            )
            for schema_name, table_name, comment in table_rows:
                result.setdefault(schema_name, {})[table_name] = {
                    "comment": comment if comment else None,
                    "columns": {},
                }

            # Column comments
            col_rows = self.execute(
                f"SELECT schema_name, table_name, column_name, comment FROM duckdb_columns() WHERE {where_clause}",
                tuple(params),
            )
            for schema_name, table_name, col_name, comment in col_rows:
                if comment:
                    result.setdefault(schema_name, {}).setdefault(table_name, {"comment": None, "columns": {}})
                    result[schema_name][table_name]["columns"][col_name] = comment
        except Exception:
            pass
        return result


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

class SchemaExcelConnector(BaseConnector):
    """Connector for Excel-based data model definitions.

    Reads two sheets from an Excel workbook:
      - 'schemas': columns with schema, table, column, primary key, foreign key, data type, etc.
      - 'relations': table relationships (table, reference table, key, reference key)

    This is a metadata-only connector — no SQL execution.
    """

    _TYPE_MAP = {
        "string": "VARCHAR",
        "date": "DATE",
        "number": "DOUBLE",
        "integer": "INTEGER",
    }

    def connect(self) -> None:
        import pandas as pd
        file_path = self.config.get("file", "")
        if not Path(file_path).is_absolute():
            file_path = str(Path(self.config.get("_root", ".")) / file_path)
        self._file_path = file_path
        self._schemas_df = pd.read_excel(file_path, sheet_name="schemas")
        try:
            self._relations_df = pd.read_excel(file_path, sheet_name="relations")
        except ValueError:
            self._relations_df = pd.DataFrame(columns=["table", "reference table", "key", "reference key"])

    def execute(self, query: str, params: tuple = ()) -> list[tuple]:
        raise NotImplementedError("ExcelConnector is metadata-only; SQL execution is not supported.")

    def _fetch_schema_rows(self, schemas_filter: list[str] | None = None) -> list[tuple]:
        df = self._schemas_df
        assert df is not None, "connect() must be called before fetching schema rows"
        if schemas_filter:
            df = df[df["schema"].isin(schemas_filter)]
        rows = []
        for _, r in df.iterrows():
            rows.append((
                r["schema"],
                r["table"],
                r["column"],
                self._normalize_type(r.get("data type")),
                "NO" if r.get("is mandatory") is True else "YES",
                None,
            ))
        return rows

    def get_schemas(self) -> list[dict]:
        """Override to include descriptions from the Excel."""
        import pandas as pd
        schemas_filter = self.config.get("schemas")
        df = self._schemas_df
        assert df is not None, "connect() must be called before fetching schemas"
        if schemas_filter:
            df = df[df["schema"].isin(schemas_filter)]

        schemas: dict[str, dict[str, dict]] = {}
        for (schema_name, table_name), group in df.groupby(["schema", "table"], sort=False):
            schema_name = str(schema_name)
            table_name = str(table_name)
            table_desc = group["table description"].iloc[0]
            if pd.isna(table_desc):
                table_desc = None

            columns = []
            for _, row in group.iterrows():
                col_desc = row.get("column description", "")
                if pd.isna(col_desc):
                    col_desc = ""
                if ": " in str(col_desc):
                    col_desc = col_desc.split(": ", 1)[1]

                columns.append({
                    "name": row["column"],
                    "description": col_desc or None,
                    "data_type": self._normalize_type(row.get("data type")),
                })

            schemas.setdefault(schema_name, {})[table_name] = {
                "description": table_desc,
                "columns": columns,
            }

        return [
            {
                "name": s_name,
                "tables": [
                    {"name": t_name, "description": t_info["description"], "columns": t_info["columns"]}
                    for t_name, t_info in tables.items()
                ],
            }
            for s_name, tables in schemas.items()
        ]

    def fetch_constraints(self, schema_name: str) -> dict[str, dict]:
        import pandas as pd
        df = self._schemas_df
        assert df is not None, "connect() must be called before fetching constraints"
        df = df[df["schema"] == schema_name]

        result: dict[str, dict] = {}

        for table_name, group in df.groupby("table", sort=False):
            table_name = str(table_name)
            pk_cols = []
            fk_cols = []
            for _, row in group.iterrows():
                pk_val = row.get("primary key")
                if pk_val is True or str(pk_val).strip().lower() == "true":
                    pk_cols.append(row["column"])
                fk_val = row.get("foreign key")
                if fk_val is True or str(fk_val).strip().lower() == "true":
                    fk_cols.append(row["column"])

            result[table_name] = {
                "primary_key": pk_cols,
                "foreign_keys": fk_cols,
                "relations": self._get_relations_for_table(table_name),
            }

        return result

    def _get_relations_for_table(self, table_name: str) -> list[dict]:
        """Build relations for a table from the relations sheet."""
        df = self._relations_df
        assert df is not None, "connect() must be called before fetching relations"
        # child table is in 'reference table' column
        child_rows = df[df["reference table"] == table_name]
        if child_rows.empty:
            return []

        relations = []
        for parent_table, group in child_rows.groupby("table", sort=False):
            pairs = sorted(zip(group["reference key"], group["key"]))
            relations.append({
                "reference_table": parent_table,
                "columns": [p[0] for p in pairs],
                "reference_table_columns": [p[1] for p in pairs],
            })
        return relations

    @classmethod
    def _normalize_type(cls, raw) -> str:
        import pandas as pd
        if not raw or pd.isna(raw):
            return "VARCHAR"
        raw_lower = str(raw).strip().lower()
        base = raw_lower.split("(")[0]
        return cls._TYPE_MAP.get(base, "VARCHAR")

    def close(self) -> None:
        self._schemas_df = None
        self._relations_df = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_CONNECTOR_MAP: dict[str, type[BaseConnector]] = {
    "duckdb": DuckDBConnector,
    "schema_excel": SchemaExcelConnector,
}


def load_connector(config: dict[str, Any]) -> BaseConnector:
    """Instantiate the right connector from a connection config dict."""
    conn_type = config.get("type", "").lower()
    cls = _CONNECTOR_MAP.get(conn_type)
    if cls is None:
        raise ValueError(
            f"Unsupported connection type '{conn_type}'. "
            f"Supported: {list(_CONNECTOR_MAP)}"
        )
    return cls(config)
