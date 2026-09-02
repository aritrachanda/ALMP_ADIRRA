"""Pydantic schemas for glossary endpoints."""
from __future__ import annotations

from pydantic import BaseModel


class GlossaryTermSchema(BaseModel):
    id: str = ""
    domain: str = ""
    category: str = ""
    title: str = ""
    business_description: str = ""
    detailed_description: str = ""
    synonyms: list[str] = []
    related_objects: list[str] = []
    steward: str = ""
    tags: list[str] = []
    status: str = "draft"
    CRR_context: str = ""
    DPM_context: str = ""
    ai_generated_fields: list[str] = []
    last_updated: str | None = None
    last_reviewed: str | None = None


class UncoveredConcept(BaseModel):
    kind: str
    dataset: str
    schema_name: str = ""
    table: str
    column: str
    data_type: str = ""
    description: str = ""
    related_object: str = ""
