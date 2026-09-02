"""Pydantic schemas for annotation endpoints."""
from __future__ import annotations

from pydantic import BaseModel


class ColumnAnnotation(BaseModel):
    user_description: str | None = None
    mapping_instructions: str | None = None


class TableAnnotation(BaseModel):
    user_description: str | None = None
    mapping_instructions: str | None = None
    columns: dict[str, ColumnAnnotation] = {}


class AnnotationOverlay(BaseModel):
    version: int = 1
    dataset: str = ""
    annotations: dict[str, TableAnnotation] = {}
