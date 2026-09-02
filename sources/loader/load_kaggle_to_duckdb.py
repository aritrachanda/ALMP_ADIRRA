"""Load Kaggle source files into a DuckDB schema.

Loads the files under ``sources/original`` into the shared in-repo DuckDB
file used for onboarding external sources (``sources/duckdb``).
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import duckdb


_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _ROOT / "sources" / "duckdb" / "almb_faker_kaggle.duckdb"
DATA_DIR = _ROOT / "sources" / "original"
SCHEMA_NAME = "raw_kaggle"


def _next_load_id(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(load_id), 0) + 1 FROM meta.load_log").fetchone()
    return int(row[0])


def _log_load(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    source_file: str,
    row_count: int,
    status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO meta.load_log (load_id, table_schema, table_name, source_file, row_count, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [_next_load_id(conn), SCHEMA_NAME, table_name, source_file, row_count, status],
    )


def _load_csv(conn: duckdb.DuckDBPyConnection, table_name: str, file_path: Path) -> int:
    conn.execute(
        f'CREATE OR REPLACE TABLE {SCHEMA_NAME}."{table_name}" AS '
        f"SELECT * FROM read_csv_auto('{file_path.as_posix()}', header=true, ignore_errors=true)"
    )
    row_count = conn.execute(f'SELECT COUNT(*) FROM {SCHEMA_NAME}."{table_name}"').fetchone()[0]
    _log_load(conn, table_name=table_name, source_file=str(file_path), row_count=row_count, status="success")
    return int(row_count)


def _load_mcc_codes(conn: duckdb.DuckDBPyConnection, file_path: Path) -> int:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    rows = [(str(code), str(description)) for code, description in data.items()]
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {SCHEMA_NAME}.mcc_codes (
            mcc_code VARCHAR,
            description VARCHAR
        )
        """
    )
    conn.executemany(f"INSERT INTO {SCHEMA_NAME}.mcc_codes VALUES (?, ?)", rows)
    _log_load(conn, table_name="mcc_codes", source_file=str(file_path), row_count=len(rows), status="success")
    return len(rows)


def _load_fraud_labels(conn: duckdb.DuckDBPyConnection, file_path: Path) -> int:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    labels = data.get("target", data) if isinstance(data, dict) else data
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name
            writer = csv.writer(tmp)
            writer.writerow(["transaction_id", "fraud_label"])
            for transaction_id, label in labels.items():
                writer.writerow([int(transaction_id), str(label)])

        conn.execute(
            f'CREATE OR REPLACE TABLE {SCHEMA_NAME}.train_fraud_labels AS '
            f"SELECT * FROM read_csv_auto('{Path(tmp_path).as_posix()}', header=true)"
        )
        row_count = conn.execute(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.train_fraud_labels").fetchone()[0]
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink()

    _log_load(
        conn,
        table_name="train_fraud_labels",
        source_file=str(file_path),
        row_count=row_count,
        status="success",
    )
    return row_count


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB file not found: {DB_PATH}")
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Kaggle data directory not found: {DATA_DIR}")

    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
        conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta.load_log (
                load_id INTEGER,
                table_schema VARCHAR,
                table_name VARCHAR,
                source_file VARCHAR,
                row_count INTEGER,
                loaded_at TIMESTAMP DEFAULT current_timestamp,
                status VARCHAR
            )
            """
        )

        load_counts = {}
        for table_name, loader in [
            ("users_data", lambda: _load_csv(conn, "users_data", DATA_DIR / "users_data.csv")),
            ("cards_data", lambda: _load_csv(conn, "cards_data", DATA_DIR / "cards_data.csv")),
            ("transactions_data", lambda: _load_csv(conn, "transactions_data", DATA_DIR / "transactions_data.csv")),
            ("mcc_codes", lambda: _load_mcc_codes(conn, DATA_DIR / "mcc_codes.json")),
            ("train_fraud_labels", lambda: _load_fraud_labels(conn, DATA_DIR / "train_fraud_labels.json")),
        ]:
            print(f"Loading {table_name}...")
            load_counts[table_name] = loader()
            print(f"  {table_name}: {load_counts[table_name]:,} rows")
    finally:
        conn.close()

    print(f"Loaded {len(load_counts)} Kaggle tables into {DB_PATH}::{SCHEMA_NAME}")
    for table_name, row_count in load_counts.items():
        print(f"  {table_name}: {row_count:,} rows")


if __name__ == "__main__":
    main()