"""Repository for the Postgres-backed source catalog (Phase 3).

Speaks the same shape callers already get from core.catalog.load_catalog_with_annotations
(schemas -> tables -> columns dicts, plus a flat top-level ``columns`` list reconstructed at
read time — not stored twice, unlike today's YAML). Annotations (.annotations.yaml) merge in
exactly as they do today (core.annotations) — that overlay stays YAML, out of scope here.

Write paths:
  * save_catalog()        — whole-source rebuild (initial build / full catalog rebuild).
  * upsert_table_profile() — single-table profile refresh: updates only that dataset's row +
    its elements, logs a catalog_refresh_event (always), and appends a snapshot row only when
    something actually changed (fingerprint dedupe, D8) with bounded retention (D8, mirrors
    core.dq_score_store's keep-first-plus-latest-N pattern).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from core.annotations import get_table_annotations, load_annotations
from core.glossary_db.db import session_scope
from core.shared.json_utils import json_default
from core.shared.models import (
    CatalogDataset,
    CatalogDatasetSnapshot,
    CatalogElement,
    CatalogElementSnapshot,
    CatalogRefreshEvent,
    CatalogSource,
)

_DEFAULT_SNAPSHOT_RETENTION = 50

# Fields captured in the fingerprint/snapshot — everything except identity/FK columns and
# fields set structurally elsewhere (schema_name/table_name/column_name/qualified_column_name/
# ordinal/etc are handled explicitly by the caller, not part of the "did the stats change"
# comparison).
DATASET_STAT_FIELDS = (
    "description", "row_count", "row_count_error", "primary_key", "inferred_primary_key",
    "foreign_keys", "relations", "duplicate_count", "duplicate_pct", "orphan_fk_count",
    "completeness_summary", "pct_columns_described", "content_hash", "source_modified_at",
    "size_bytes", "file_count", "format_hint",
)

ELEMENT_STAT_FIELDS = (
    "data_type", "description", "type_distribution", "array_length_min", "array_length_max",
    "array_length_avg", "row_count", "null_count", "null_pct", "distinct_count",
    "duplicate_count", "uniqueness_pct", "empty_string_count", "placeholder_count",
    "min_value", "max_value", "length_min", "length_max", "length_avg", "inferred_pattern",
    "pattern_confidence", "invalid_format_count", "code_values", "value_distribution",
    "numeric_avg", "numeric_median", "numeric_stddev", "numeric_outlier_count",
    "outlier_detection", "decimal_scale_distribution", "future_date_count",
    "suspicious_date_count", "type_mismatch_count", "validator_pass_rates",
    "constant_run_warning", "stats_error", "sample_values", "top_values",
)

# ── add-profile-reset (D5): a NEW, narrower field list — deliberately NOT a reuse of
# DATASET_STAT_FIELDS/ELEMENT_STAT_FIELDS above. Those exist to answer "did the stats change?"
# (fingerprinting/snapshots) and include `description`, `data_type`, `primary_key`,
# `foreign_keys`, `relations` — precisely the fields that must SURVIVE a reset. The provenance
# rule: reset clears what came from reading the data; it preserves what came from onboarding-time
# metadata extraction (column identity, declared PK/FK/relations, descriptions).
#
# `content_hash`/`source_modified_at`/`size_bytes`/`file_count`/`format_hint` are file-based-
# source metadata (only ever populated by a hypothetical directory/blob scan, never by today's
# DuckDB connector) — treated as profiling-derived (cleared) since nothing in this codebase
# populates them at onboarding time today.
PROFILE_DERIVED_DATASET_FIELDS = (
    "row_count", "row_count_error", "inferred_primary_key", "duplicate_count", "duplicate_pct",
    "orphan_fk_count", "completeness_summary", "pct_columns_described", "content_hash",
    "source_modified_at", "size_bytes", "file_count", "format_hint",
)

# D5's two open items, resolved:
#  - `inferred_relations` has NO CatalogDataset/CatalogElement column at all — it is never in
#    DATASET_STAT_FIELDS, so upsert_table_profile()/_apply_fields() never persists it. It is a
#    purely ephemeral attribute `core.extractors.profiler._infer_relations_for_schema` attaches
#    to an in-memory table dict computed live at profile-compute time (from column names/types
#    and the DECLARED `primary_key`/`relations`, both preserved by reset), never read back from
#    storage. A reset therefore cannot leave it stale — there is nothing stored to go stale.
#  - `type_distribution`/`array_length_*` (nested/schema-on-read structural discovery for
#    JSON/Parquet-style sources) are treated as profiling-derived (cleared) for now: the only
#    connector in this codebase (DuckDB) is fully scalar/tabular and never populates them at
#    onboarding time, so there is no "onboarding-owned" value they could preserve today. Revisit
#    if a nested/schema-on-read connector is ever added.
PROFILE_DERIVED_ELEMENT_FIELDS = tuple(
    f for f in ELEMENT_STAT_FIELDS if f not in ("data_type", "description")
)

#: The sole "not profiled" sentinel for `profiling_status`, per its CHECK constraint in
#: db/migrations/versions/0008_add_source_catalog.py (`'discovered'|'profiled'|'failed'|
#: 'excluded'`) — the same status a freshly-onboarded, never-profiled table already rests in.
NOT_PROFILED_STATUS = "discovered"


def _apply_fields(obj: Any, data: dict, fields: tuple[str, ...]) -> None:
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])


def _fingerprint(values: dict) -> str:
    canonical = json.dumps(values, sort_keys=True, default=json_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_values(obj: Any, fields: tuple[str, ...]) -> dict:
    # NUMERIC columns come back from Postgres as Decimal; callers (element.py, DQ scoring,
    # fingerprinting) expect plain floats, same shape YAML always gave them.
    return {f: _to_plain(getattr(obj, f)) for f in fields}


def _to_plain(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _prune_snapshots(session, model, fk_field: str, fk_value: int,
                     max_records: int = _DEFAULT_SNAPSHOT_RETENTION) -> None:
    """Keep the oldest (baseline) + latest ``max_records - 1``, prune the middle.

    Mirrors core.dq_score_store.DQScoreStore._prune_locked's retention rule, as a SQL delete
    instead of a Python list-slice (D8).
    """
    ids = session.execute(
        select(model.id).where(getattr(model, fk_field) == fk_value).order_by(model.captured_at.desc())
    ).scalars().all()
    if len(ids) <= max_records:
        return
    baseline = ids[-1]
    keep = set(ids[: max_records - 1])
    keep.add(baseline)
    to_delete = [i for i in ids if i not in keep]
    if to_delete:
        session.execute(delete(model).where(model.id.in_(to_delete)))


# ── reads ────────────────────────────────────────────────────────────────────

def list_source_names(kind: str = "source") -> list[str]:
    """Return the names of every catalog of *kind* ("source" or "target"), sorted.

    Postgres-backed counterpart of the YAML-mode ``catalog_dir.glob("*.yaml")`` listing —
    used by ``api.routes.catalogs.list_catalogs`` so the "which sources/targets exist"
    discovery endpoint stays in sync with the catalog_backend flag, instead of only ever
    reading the on-disk YAML directory regardless of backend (TD).
    """
    with session_scope() as s:
        return sorted(
            s.execute(
                select(CatalogSource.source_name).where(CatalogSource.kind == kind)
            ).scalars().all()
        )


def load_catalog(source_name: str, kind: str = "source", catalog_dir: Path | None = None) -> dict:
    """Return the catalog for *source_name*, in the same shape as
    core.catalog.load_catalog_with_annotations, merging annotations from *catalog_dir* if given.
    """
    with session_scope() as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
        ).scalar_one_or_none()
        if source is None:
            return {}

        datasets = s.execute(
            select(CatalogDataset).where(CatalogDataset.source_id == source.source_id)
            .order_by(CatalogDataset.schema_name, CatalogDataset.table_name)
        ).scalars().all()
        dataset_ids = [d.dataset_id for d in datasets]

        elements_by_dataset: dict[int, list[CatalogElement]] = defaultdict(list)
        if dataset_ids:
            elements = s.execute(
                select(CatalogElement)
                .where(CatalogElement.dataset_id.in_(dataset_ids), CatalogElement.parent_element_id.is_(None))
                .order_by(CatalogElement.dataset_id, CatalogElement.ordinal)
            ).scalars().all()
            for e in elements:
                elements_by_dataset[e.dataset_id].append(e)

        annotations = load_annotations(source_name, catalog_dir) if catalog_dir else None

        schemas_map: dict[str, dict] = {}
        flat_columns: list[dict] = []
        for ds in datasets:
            schema_entry = schemas_map.setdefault(ds.schema_name, {"name": ds.schema_name, "tables": []})
            table_anno = (
                get_table_annotations(annotations, ds.schema_name, ds.table_name)
                if annotations else {"user_description": "", "mapping_instructions": "", "columns": {}}
            )
            table_dict: dict[str, Any] = {
                "schema_name": ds.schema_name, "table_name": ds.table_name,
                "description": ds.description, "row_count": ds.row_count,
                "row_count_error": ds.row_count_error,
                "primary_key": ds.primary_key or [], "inferred_primary_key": ds.inferred_primary_key or [],
                "foreign_keys": ds.foreign_keys or [], "relations": ds.relations or [],
                "duplicate_count": ds.duplicate_count, "duplicate_pct": _to_plain(ds.duplicate_pct),
                "orphan_fk_count": ds.orphan_fk_count, "completeness_summary": _to_plain(ds.completeness_summary),
                "pct_columns_described": _to_plain(ds.pct_columns_described),
                # This table's own last-profiled time — distinct from the source-level
                # generated_at below, which moves on every table's write (TD#26).
                "profiled_at": ds.profiled_at.isoformat() if ds.profiled_at else None,
                "columns": [],
            }
            if table_anno.get("user_description"):
                table_dict["user_description"] = table_anno["user_description"]
            if table_anno.get("mapping_instructions"):
                table_dict["mapping_instructions"] = table_anno["mapping_instructions"]

            col_annos = table_anno.get("columns", {}) or {}
            for el in elements_by_dataset.get(ds.dataset_id, []):
                col: dict[str, Any] = {"name": el.column_name, "ordinal": el.ordinal}
                col.update(_snapshot_values(el, ELEMENT_STAT_FIELDS))
                col_anno = col_annos.get(el.column_name)
                if col_anno:
                    if col_anno.get("user_description"):
                        col["user_description"] = col_anno["user_description"]
                    if col_anno.get("mapping_instructions"):
                        col["mapping_instructions"] = col_anno["mapping_instructions"]
                table_dict["columns"].append(col)
                flat_columns.append({
                    "source": source_name, "schema": ds.schema_name, "table": ds.table_name,
                    "table_description": ds.description, **col,
                })

            schema_entry["tables"].append(table_dict)

        return {
            "version": source.version,
            "source": source.source_name,
            "connection": source.connection_ref,
            "generated_at": source.generated_at.isoformat() if source.generated_at else None,
            "schema_hash": source.schema_hash,
            "schemas": list(schemas_map.values()),
            "columns": flat_columns,
        }


# ── writes ───────────────────────────────────────────────────────────────────

def save_catalog(
    source_name: str, *, kind: str = "source", connector_type: str | None = None,
    connection_ref: str | None = None, legal_entity: str | None = None,
    version: int | None = None, schema_hash: str | None = None,
    generated_at: datetime | None = None, schemas: list[dict] | None = None,
) -> None:
    """Whole-source save/rebuild — mirrors catalog_builder.save_catalog's full-overwrite
    semantics (used for the initial build, not the everyday single-table refresh path)."""
    with session_scope() as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
        ).scalar_one_or_none()
        if source is None:
            source = CatalogSource(source_name=source_name, kind=kind)
            s.add(source)
            s.flush()
        source.connector_type = connector_type
        source.connection_ref = connection_ref
        source.legal_entity = legal_entity
        source.version = version
        source.schema_hash = schema_hash
        source.generated_at = generated_at

        existing = s.execute(select(CatalogDataset).where(CatalogDataset.source_id == source.source_id)).scalars().all()
        for ds in existing:
            s.delete(ds)
        s.flush()

        for schema in schemas or []:
            for tbl in schema.get("tables", []):
                dataset = CatalogDataset(
                    source_id=source.source_id,
                    schema_name=schema.get("name") or tbl.get("schema_name"),
                    table_name=tbl.get("table_name"),
                    profiling_status="profiled",
                )
                _apply_fields(dataset, tbl, DATASET_STAT_FIELDS)
                s.add(dataset)
                s.flush()
                for idx, col in enumerate(tbl.get("columns", []) or []):
                    name = col.get("name")
                    if not name:
                        continue
                    element = CatalogElement(
                        dataset_id=dataset.dataset_id, qualified_column_name=name,
                        column_name=name, ordinal=idx,
                    )
                    _apply_fields(element, col, ELEMENT_STAT_FIELDS)
                    s.add(element)


def upsert_table_profile(
    source_name: str, schema_name: str, table_name: str, profile: dict,
    *, kind: str = "source", triggered_by: str | None = None,
) -> None:
    """Single-table profile refresh: updates only this dataset's row + its elements (no
    other table in the source is touched), logs a catalog_refresh_event (always), and
    appends snapshot rows only when something actually changed (D8)."""
    with session_scope() as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
        ).scalar_one_or_none()
        if source is None:
            raise ValueError(f"catalog_source not found for source_name={source_name!r}, kind={kind!r}")

        dataset = s.execute(
            select(CatalogDataset).where(
                CatalogDataset.source_id == source.source_id,
                CatalogDataset.schema_name == schema_name,
                CatalogDataset.table_name == table_name,
            )
        ).scalar_one_or_none()
        if dataset is None:
            dataset = CatalogDataset(source_id=source.source_id, schema_name=schema_name, table_name=table_name)
            s.add(dataset)
            s.flush()

        _apply_fields(dataset, profile, DATASET_STAT_FIELDS)
        dataset.profiled_at = datetime.now(timezone.utc)
        dataset.profiling_status = "failed" if profile.get("row_count_error") else "profiled"
        # Mirrors the YAML branch (_write_table_profile_yaml bumps the catalog's
        # top-level generated_at on every table write) — without this, the source-level
        # "Profiled" timestamp only ever moved on a full catalog rebuild, never on an
        # everyday single-table or bulk per-table refresh.
        source.generated_at = datetime.now(timezone.utc)
        s.flush()

        dataset_fp = _fingerprint(_snapshot_values(dataset, DATASET_STAT_FIELDS))
        latest_ds_snap = s.execute(
            select(CatalogDatasetSnapshot).where(CatalogDatasetSnapshot.dataset_id == dataset.dataset_id)
            .order_by(CatalogDatasetSnapshot.captured_at.desc()).limit(1)
        ).scalar_one_or_none()
        dataset_changed = latest_ds_snap is None or latest_ds_snap.fingerprint != dataset_fp
        if dataset_changed:
            snap = CatalogDatasetSnapshot(
                dataset_id=dataset.dataset_id, fingerprint=dataset_fp,
                schema_name=dataset.schema_name, table_name=dataset.table_name,
            )
            _apply_fields(snap, profile, DATASET_STAT_FIELDS)
            s.add(snap)
            s.flush()
            _prune_snapshots(s, CatalogDatasetSnapshot, "dataset_id", dataset.dataset_id)

        existing_elements = {
            e.column_name: e for e in s.execute(
                select(CatalogElement).where(
                    CatalogElement.dataset_id == dataset.dataset_id,
                    CatalogElement.parent_element_id.is_(None),
                )
            ).scalars().all()
        }
        seen_names: set[str] = set()
        any_element_changed = False
        for idx, col in enumerate(profile.get("columns", []) or []):
            name = col.get("name")
            if not name:
                continue
            seen_names.add(name)
            element = existing_elements.get(name)
            if element is None:
                element = CatalogElement(
                    dataset_id=dataset.dataset_id, qualified_column_name=name,
                    column_name=name, ordinal=idx,
                )
                s.add(element)
                s.flush()
            else:
                element.ordinal = idx
            _apply_fields(element, col, ELEMENT_STAT_FIELDS)
            s.flush()

            el_fp = _fingerprint(_snapshot_values(element, ELEMENT_STAT_FIELDS))
            latest_el_snap = s.execute(
                select(CatalogElementSnapshot).where(CatalogElementSnapshot.element_id == element.element_id)
                .order_by(CatalogElementSnapshot.captured_at.desc()).limit(1)
            ).scalar_one_or_none()
            if latest_el_snap is None or latest_el_snap.fingerprint != el_fp:
                any_element_changed = True
                el_snap = CatalogElementSnapshot(
                    element_id=element.element_id, fingerprint=el_fp,
                    parent_element_id=element.parent_element_id,
                    qualified_column_name=element.qualified_column_name,
                    column_name=element.column_name, column_kind=element.column_kind,
                    nesting_level=element.nesting_level, ordinal=element.ordinal,
                )
                _apply_fields(el_snap, col, ELEMENT_STAT_FIELDS)
                s.add(el_snap)
                s.flush()
                _prune_snapshots(s, CatalogElementSnapshot, "element_id", element.element_id)

        # Columns no longer present in this refresh (schema drift) are removed.
        for name, element in existing_elements.items():
            if name not in seen_names:
                s.delete(element)

        s.add(CatalogRefreshEvent(
            dataset_id=dataset.dataset_id, triggered_by=triggered_by,
            changed=bool(dataset_changed or any_element_changed),
        ))


# ── add-profile-reset: clear profiling-derived stats back to a never-profiled shape ─────────
#
# Unlike every function above, these two take a caller-managed *session* rather than opening
# their own `session_scope()` — the reset orchestrator wraps every store's clear in ONE shared
# transaction (design.md D3), so this module must never commit on its own behalf here.

def clear_table_stats(
    session, source_name: str, schema_name: str, table_name: str, *,
    kind: str = "source", triggered_by: str | None = None,
) -> dict[str, int]:
    """Clear one table's profiling-derived catalog stats back to a never-profiled shape.

    Snapshots the CURRENT dataset/element rows first — the same append-only history
    ``upsert_table_profile`` already writes on an ordinary refresh (D9's soft-reset: nothing is
    hard-deleted here, only nulled after being captured) — then nulls only
    ``PROFILE_DERIVED_DATASET_FIELDS``/``PROFILE_DERIVED_ELEMENT_FIELDS``, preserving column
    identity (name/``data_type``/``description``) and declared schema metadata
    (``description``/``primary_key``/``foreign_keys``/``relations``) per D5.

    Idempotent: calling this on an already-cleared table is a no-op (returns zero counts,
    writes no new snapshot). Returns ``{"dataset": 0 or 1, "element": <count cleared>}``.
    """
    source = session.execute(
        select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
    ).scalar_one_or_none()
    if source is None:
        return {"dataset": 0, "element": 0}

    dataset = session.execute(
        select(CatalogDataset).where(
            CatalogDataset.source_id == source.source_id,
            CatalogDataset.schema_name == schema_name,
            CatalogDataset.table_name == table_name,
        )
    ).scalar_one_or_none()
    if dataset is None:
        return {"dataset": 0, "element": 0}

    elements = session.execute(
        select(CatalogElement).where(
            CatalogElement.dataset_id == dataset.dataset_id,
            CatalogElement.parent_element_id.is_(None),
        )
    ).scalars().all()

    already_clear = (
        dataset.profiling_status == NOT_PROFILED_STATUS
        and dataset.profiled_at is None
        and not any(getattr(dataset, f) is not None for f in PROFILE_DERIVED_DATASET_FIELDS)
        and not any(
            getattr(el, f) is not None for el in elements for f in PROFILE_DERIVED_ELEMENT_FIELDS
        )
    )
    if already_clear:
        return {"dataset": 0, "element": 0}

    # Snapshot BEFORE clearing — same fingerprint-dedupe + bounded retention as
    # upsert_table_profile, so a reset never bypasses the existing snapshot history.
    dataset_fp = _fingerprint(_snapshot_values(dataset, DATASET_STAT_FIELDS))
    latest_ds_snap = session.execute(
        select(CatalogDatasetSnapshot).where(CatalogDatasetSnapshot.dataset_id == dataset.dataset_id)
        .order_by(CatalogDatasetSnapshot.captured_at.desc()).limit(1)
    ).scalar_one_or_none()
    if latest_ds_snap is None or latest_ds_snap.fingerprint != dataset_fp:
        snap = CatalogDatasetSnapshot(
            dataset_id=dataset.dataset_id, fingerprint=dataset_fp,
            schema_name=dataset.schema_name, table_name=dataset.table_name,
        )
        _apply_fields(snap, {f: getattr(dataset, f) for f in DATASET_STAT_FIELDS}, DATASET_STAT_FIELDS)
        session.add(snap)
        session.flush()
        _prune_snapshots(session, CatalogDatasetSnapshot, "dataset_id", dataset.dataset_id)

    for field in PROFILE_DERIVED_DATASET_FIELDS:
        setattr(dataset, field, None)
    dataset.profiling_status = NOT_PROFILED_STATUS
    dataset.profiled_at = None

    cleared_elements = 0
    for element in elements:
        el_fp = _fingerprint(_snapshot_values(element, ELEMENT_STAT_FIELDS))
        latest_el_snap = session.execute(
            select(CatalogElementSnapshot).where(CatalogElementSnapshot.element_id == element.element_id)
            .order_by(CatalogElementSnapshot.captured_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_el_snap is None or latest_el_snap.fingerprint != el_fp:
            el_snap = CatalogElementSnapshot(
                element_id=element.element_id, fingerprint=el_fp,
                parent_element_id=element.parent_element_id,
                qualified_column_name=element.qualified_column_name,
                column_name=element.column_name, column_kind=element.column_kind,
                nesting_level=element.nesting_level, ordinal=element.ordinal,
            )
            _apply_fields(el_snap, {f: getattr(element, f) for f in ELEMENT_STAT_FIELDS}, ELEMENT_STAT_FIELDS)
            session.add(el_snap)
            session.flush()
            _prune_snapshots(session, CatalogElementSnapshot, "element_id", element.element_id)
        for field in PROFILE_DERIVED_ELEMENT_FIELDS:
            setattr(element, field, None)
        cleared_elements += 1

    session.add(CatalogRefreshEvent(
        dataset_id=dataset.dataset_id, triggered_by=triggered_by, changed=True,
    ))
    return {"dataset": 1, "element": cleared_elements}


def clear_source_stats(
    session, source_name: str, *, kind: str = "source", triggered_by: str | None = None,
) -> dict[str, int]:
    """Clear every table in *source_name* per :func:`clear_table_stats`.

    Also clears the source-level ``generated_at`` — no longer true once every table in the
    source is unprofiled again. A single-table reset (:func:`clear_table_stats` alone) leaves
    ``generated_at`` untouched, since other tables in the source may still be profiled.
    """
    source = session.execute(
        select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
    ).scalar_one_or_none()
    if source is None:
        return {"dataset": 0, "element": 0}

    datasets = session.execute(
        select(CatalogDataset).where(CatalogDataset.source_id == source.source_id)
    ).scalars().all()

    totals = {"dataset": 0, "element": 0}
    for dataset in datasets:
        result = clear_table_stats(
            session, source_name, dataset.schema_name, dataset.table_name,
            kind=kind, triggered_by=triggered_by,
        )
        totals["dataset"] += result["dataset"]
        totals["element"] += result["element"]

    source.generated_at = None
    return totals


def is_profiled(source_name: str, schema_name: str, table_name: str, *, kind: str = "source") -> bool:
    """D11 (add-profile-reset) — the single authoritative answer to "has this table been
    profiled?", reading ``catalog_dataset.profiling_status`` directly.

    Every other caller (API, UI) must route through this rather than inferring "unprofiled" by
    checking for absence in some other store (DQ score, semantic type, etc.) — those
    representations can drift out of sync with each other; this one cannot, because it is the
    only place written to.

    Deliberately keyed on ``profiling_status`` alone, NOT also ``profiled_at`` — a whole-source
    rebuild (``save_catalog``) sets ``profiling_status='profiled'`` but never populates
    ``profiled_at`` (only the per-table refresh path, ``upsert_table_profile``, does), so
    requiring both would misreport a table as unprofiled right after a full catalog rebuild.
    Anything other than the ``'discovered'``/absent "never profiled yet" state — including
    ``'failed'`` (a profiling attempt was made, even if it errored) and ``'excluded'`` — counts
    as profiled for this purpose.
    """
    with session_scope() as s:
        source = s.execute(
            select(CatalogSource).where(CatalogSource.source_name == source_name, CatalogSource.kind == kind)
        ).scalar_one_or_none()
        if source is None:
            return False
        dataset = s.execute(
            select(CatalogDataset).where(
                CatalogDataset.source_id == source.source_id,
                CatalogDataset.schema_name == schema_name,
                CatalogDataset.table_name == table_name,
            )
        ).scalar_one_or_none()
        if dataset is None:
            return False
        return dataset.profiling_status not in (None, NOT_PROFILED_STATUS)
