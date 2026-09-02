"""Catalog feature models — moved from core/glossary_db/models.py (S0 models split).

Mirrors db/migrations/versions/0008_add_source_catalog.py — that hand-written DDL remains the
source of truth (CHECK constraints, generated identity columns).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.shared.models.base import Base


class CatalogSource(Base):
    """Source/target catalog root (source-catalog YAML -> Postgres migration, Phase 3)."""
    __tablename__ = "catalog_source"
    id_field = "source_id"
    source_id: Mapped[int] = mapped_column("source_id", BigInteger, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    connector_type: Mapped[str | None] = mapped_column(Text)
    connection_ref: Mapped[str | None] = mapped_column(Text)
    legal_entity: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int | None] = mapped_column(Integer)
    schema_hash: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    datasets: Mapped[list["CatalogDataset"]] = relationship(
        back_populates="source", cascade="all, delete-orphan")


class CatalogDataset(Base):
    __tablename__ = "catalog_dataset"
    __table_args__ = (UniqueConstraint("source_id", "schema_name", "table_name"),)
    dataset_id: Mapped[int] = mapped_column("dataset_id", BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_source.source_id", ondelete="CASCADE"), nullable=False)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    row_count_error: Mapped[str | None] = mapped_column(Text)
    primary_key: Mapped[list | None] = mapped_column(JSONB)
    inferred_primary_key: Mapped[list | None] = mapped_column(JSONB)
    foreign_keys: Mapped[list | None] = mapped_column(JSONB)
    relations: Mapped[list | None] = mapped_column(JSONB)
    duplicate_count: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_pct: Mapped[float | None] = mapped_column(Numeric)
    orphan_fk_count: Mapped[int | None] = mapped_column(BigInteger)
    completeness_summary: Mapped[float | None] = mapped_column(Numeric)
    pct_columns_described: Mapped[float | None] = mapped_column(Numeric)
    profiled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    origin_uri: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    profiling_status: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    source_modified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_count: Mapped[int | None] = mapped_column(Integer)
    format_hint: Mapped[dict | None] = mapped_column(JSONB)

    source: Mapped["CatalogSource"] = relationship(back_populates="datasets")
    elements: Mapped[list["CatalogElement"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan")


class CatalogElement(Base):
    __tablename__ = "catalog_element"
    __table_args__ = (UniqueConstraint("dataset_id", "qualified_column_name"),)
    element_id: Mapped[int] = mapped_column("element_id", BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("catalog_dataset.dataset_id", ondelete="CASCADE"), nullable=False)
    parent_element_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_element.element_id", ondelete="CASCADE"))
    qualified_column_name: Mapped[str] = mapped_column(Text, nullable=False)
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    column_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="scalar")
    nesting_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ordinal: Mapped[int | None] = mapped_column(Integer)
    data_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    type_distribution: Mapped[dict | None] = mapped_column(JSONB)
    array_length_min: Mapped[int | None] = mapped_column(Integer)
    array_length_max: Mapped[int | None] = mapped_column(Integer)
    array_length_avg: Mapped[float | None] = mapped_column(Numeric)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    null_count: Mapped[int | None] = mapped_column(BigInteger)
    null_pct: Mapped[float | None] = mapped_column(Numeric)
    distinct_count: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_count: Mapped[int | None] = mapped_column(BigInteger)
    uniqueness_pct: Mapped[float | None] = mapped_column(Numeric)
    empty_string_count: Mapped[int | None] = mapped_column(BigInteger)
    placeholder_count: Mapped[int | None] = mapped_column(BigInteger)
    min_value: Mapped[str | None] = mapped_column(Text)
    max_value: Mapped[str | None] = mapped_column(Text)
    length_min: Mapped[int | None] = mapped_column(Integer)
    length_max: Mapped[int | None] = mapped_column(Integer)
    length_avg: Mapped[float | None] = mapped_column(Numeric)
    inferred_pattern: Mapped[str | None] = mapped_column(Text)
    pattern_confidence: Mapped[float | None] = mapped_column(Numeric)
    invalid_format_count: Mapped[int | None] = mapped_column(BigInteger)
    code_values: Mapped[list | None] = mapped_column(JSONB)
    value_distribution: Mapped[dict | None] = mapped_column(JSONB)
    numeric_avg: Mapped[float | None] = mapped_column(Numeric)
    numeric_median: Mapped[float | None] = mapped_column(Numeric)
    numeric_stddev: Mapped[float | None] = mapped_column(Numeric)
    numeric_outlier_count: Mapped[int | None] = mapped_column(BigInteger)
    outlier_detection: Mapped[str | None] = mapped_column(Text)
    decimal_scale_distribution: Mapped[dict | None] = mapped_column(JSONB)
    future_date_count: Mapped[int | None] = mapped_column(BigInteger)
    suspicious_date_count: Mapped[int | None] = mapped_column(BigInteger)
    type_mismatch_count: Mapped[int | None] = mapped_column(BigInteger)
    validator_pass_rates: Mapped[dict | None] = mapped_column(JSONB)
    constant_run_warning: Mapped[dict | None] = mapped_column(JSONB)
    stats_error: Mapped[str | None] = mapped_column(Text)
    sample_values: Mapped[list | None] = mapped_column(JSONB)
    top_values: Mapped[list | None] = mapped_column(JSONB)

    dataset: Mapped["CatalogDataset"] = relationship(back_populates="elements")


class CatalogRefreshEvent(Base):
    __tablename__ = "catalog_refresh_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("catalog_dataset.dataset_id", ondelete="CASCADE"), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(Text)
    changed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CatalogDatasetSnapshot(Base):
    """Append-only history of catalog_dataset (D8) — one row per changed profile refresh."""
    __tablename__ = "catalog_dataset_snapshot"
    __table_args__ = (UniqueConstraint("dataset_id", "captured_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("catalog_dataset.dataset_id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    schema_name: Mapped[str | None] = mapped_column(Text)
    table_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    row_count_error: Mapped[str | None] = mapped_column(Text)
    primary_key: Mapped[list | None] = mapped_column(JSONB)
    inferred_primary_key: Mapped[list | None] = mapped_column(JSONB)
    foreign_keys: Mapped[list | None] = mapped_column(JSONB)
    relations: Mapped[list | None] = mapped_column(JSONB)
    duplicate_count: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_pct: Mapped[float | None] = mapped_column(Numeric)
    orphan_fk_count: Mapped[int | None] = mapped_column(BigInteger)
    completeness_summary: Mapped[float | None] = mapped_column(Numeric)
    pct_columns_described: Mapped[float | None] = mapped_column(Numeric)
    profiling_status: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    source_modified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_count: Mapped[int | None] = mapped_column(Integer)
    format_hint: Mapped[dict | None] = mapped_column(JSONB)


class CatalogElementSnapshot(Base):
    """Append-only history of catalog_element (D8). parent_element_id is a frozen plain
    value (no FK) — a historical snapshot must not depend on a possibly-since-changed
    live parent row's identity."""
    __tablename__ = "catalog_element_snapshot"
    __table_args__ = (UniqueConstraint("element_id", "captured_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_id: Mapped[int] = mapped_column(ForeignKey("catalog_element.element_id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    parent_element_id: Mapped[int | None] = mapped_column(BigInteger)
    qualified_column_name: Mapped[str | None] = mapped_column(Text)
    column_name: Mapped[str | None] = mapped_column(Text)
    column_kind: Mapped[str | None] = mapped_column(Text)
    nesting_level: Mapped[int | None] = mapped_column(Integer)
    ordinal: Mapped[int | None] = mapped_column(Integer)
    data_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    type_distribution: Mapped[dict | None] = mapped_column(JSONB)
    array_length_min: Mapped[int | None] = mapped_column(Integer)
    array_length_max: Mapped[int | None] = mapped_column(Integer)
    array_length_avg: Mapped[float | None] = mapped_column(Numeric)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    null_count: Mapped[int | None] = mapped_column(BigInteger)
    null_pct: Mapped[float | None] = mapped_column(Numeric)
    distinct_count: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_count: Mapped[int | None] = mapped_column(BigInteger)
    uniqueness_pct: Mapped[float | None] = mapped_column(Numeric)
    empty_string_count: Mapped[int | None] = mapped_column(BigInteger)
    placeholder_count: Mapped[int | None] = mapped_column(BigInteger)
    min_value: Mapped[str | None] = mapped_column(Text)
    max_value: Mapped[str | None] = mapped_column(Text)
    length_min: Mapped[int | None] = mapped_column(Integer)
    length_max: Mapped[int | None] = mapped_column(Integer)
    length_avg: Mapped[float | None] = mapped_column(Numeric)
    inferred_pattern: Mapped[str | None] = mapped_column(Text)
    pattern_confidence: Mapped[float | None] = mapped_column(Numeric)
    invalid_format_count: Mapped[int | None] = mapped_column(BigInteger)
    code_values: Mapped[list | None] = mapped_column(JSONB)
    value_distribution: Mapped[dict | None] = mapped_column(JSONB)
    numeric_avg: Mapped[float | None] = mapped_column(Numeric)
    numeric_median: Mapped[float | None] = mapped_column(Numeric)
    numeric_stddev: Mapped[float | None] = mapped_column(Numeric)
    numeric_outlier_count: Mapped[int | None] = mapped_column(BigInteger)
    outlier_detection: Mapped[str | None] = mapped_column(Text)
    decimal_scale_distribution: Mapped[dict | None] = mapped_column(JSONB)
    future_date_count: Mapped[int | None] = mapped_column(BigInteger)
    suspicious_date_count: Mapped[int | None] = mapped_column(BigInteger)
    type_mismatch_count: Mapped[int | None] = mapped_column(BigInteger)
    validator_pass_rates: Mapped[dict | None] = mapped_column(JSONB)
    constant_run_warning: Mapped[dict | None] = mapped_column(JSONB)
    stats_error: Mapped[str | None] = mapped_column(Text)
    sample_values: Mapped[list | None] = mapped_column(JSONB)
    top_values: Mapped[list | None] = mapped_column(JSONB)
