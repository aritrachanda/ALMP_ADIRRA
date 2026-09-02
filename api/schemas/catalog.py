"""Pydantic schemas for catalog endpoints."""
from __future__ import annotations

from pydantic import BaseModel


class Column(BaseModel):
    name: str
    description: str | None = None
    data_type: str | None = None
    row_count: int | None = None
    null_count: int | None = None
    null_pct: float | None = None
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    sample_values: list[str] | None = None


class Table(BaseModel):
    schema_name: str
    table_name: str
    description: str | None = None
    row_count: int | None = None
    primary_key: list[str] | None = None
    foreign_keys: list[str] | None = None
    relations: list[dict] | None = None
    columns: list[Column] = []


class Schema(BaseModel):
    name: str
    tables: list[Table] = []


class Catalog(BaseModel):
    version: int | None = None
    source: str | None = None
    connection: str | None = None
    generated_at: str | None = None
    schema_hash: str | None = None
    schemas: list[Schema] = []


class CatalogListItem(BaseModel):
    name: str


class CatalogList(BaseModel):
    type: str
    catalogs: list[CatalogListItem]
