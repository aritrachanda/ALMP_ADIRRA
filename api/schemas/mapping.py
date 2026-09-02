"""Pydantic schemas for mapping endpoints."""
from __future__ import annotations

from pydantic import BaseModel


class ColumnMapping(BaseModel):
    target_column: str
    source_schema: str | None = None
    source_table: str | None = None
    source_column: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    transformation_type: str | None = None
    notes: str | None = None
    status: str = "pending"


class MappingTable(BaseModel):
    target_schema: str
    target_table: str
    target_framework: str | None = None
    table_confidence: float | None = None
    table_rationale: str | None = None
    sql_query: str | None = None
    columns: list[ColumnMapping] = []


class MappingResult(BaseModel):
    version: int | None = None
    agent: str | None = None
    source: str | None = None
    target: str | None = None
    provider: str | None = None
    model: str | None = None
    generated_at: str | None = None
    status: str | None = None
    tables: list[MappingTable] = []


class MappingListItem(BaseModel):
    source: str
    target: str
    filename: str


class MappingRunRequest(BaseModel):
    dataset_context: str = ""
    agent_choice: str = "default"
    selected_tables: list[str] | None = None


class CandidateUpdate(BaseModel):
    target_schema: str
    target_table: str
    target_column: str
    status: str  # "accepted" | "discarded" | "pending"


class CandidateUpdateBatch(BaseModel):
    updates: list[CandidateUpdate]
