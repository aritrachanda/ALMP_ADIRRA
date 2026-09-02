"""Pydantic schemas for discovery endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ColumnStats(BaseModel):
    name: str
    data_type: str | None = None
    row_count: int | None = None
    null_count: int | None = None
    null_pct: float | None = None
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    sample_values: list[str] | None = None


class TableStats(BaseModel):
    schema_name: str
    table_name: str
    description: str | None = None
    row_count: int | None = None
    columns: list[ColumnStats] = []


class QueryRequest(BaseModel):
    sql: str
    limit: int = 100


class QueryResult(BaseModel):
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0
