"""
extractors  –  Schema extraction and data profiling module.

Provides:
    - extract_schema_from_db(): extract schema via information_schema
    - load_schema_yaml(): load a pre-built schema YAML file
    - enrich_schemas(): enrich schema with column-level statistics
    - fetch_constraints(): extract PK/FK constraints from DuckDB
"""
from core.extractors.schema import load_schema_yaml, extract_schema_from_db
from core.extractors.profiler import enrich_schemas

__all__ = [
    "load_schema_yaml",
    "extract_schema_from_db",
    "enrich_schemas",
]
