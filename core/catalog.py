"""Catalog loading utilities with annotation merging.

Ensures descriptions stored in annotations.yaml persist across profile refreshes
by merging them into catalog views.
"""
from datetime import datetime
from pathlib import Path
import yaml

from core.catalog_db import backend as _catalog_backend
from core.catalog_db import list_source_names as _pg_list_source_names
from core.catalog_db import load_catalog as _pg_load_catalog
from core.catalog_db import save_catalog as _pg_save_catalog
from core.catalog_db import upsert_table_profile as _pg_upsert_table_profile
from core.shared.db_availability import require_reachable


# Path-keyed cache of parsed catalogs. Invalidated when the catalog file or its
# annotations overlay changes on disk (mtime). Shared by every route so a large
# catalog (e.g. a multi-MB source) is parsed once, not re-parsed per request.
_CATALOG_CACHE: dict[str, tuple[float, dict]] = {}


def load_catalog_with_annotations_cached(catalog_path: Path) -> dict:
    """mtime-cached wrapper around :func:`load_catalog_with_annotations`.

    Re-parses only when the catalog YAML or its ``.annotations.yaml`` overlay
    changes on disk. Returns a SHARED dict — callers must treat it as read-only
    (do not mutate the returned structure).
    """
    if not catalog_path.exists():
        return {}
    mtime = catalog_path.stat().st_mtime
    anno_path = catalog_path.parent / f"{catalog_path.stem}.annotations.yaml"
    if anno_path.exists():
        mtime = max(mtime, anno_path.stat().st_mtime)
    key = str(catalog_path)
    cached = _CATALOG_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    catalog = load_catalog_with_annotations(catalog_path)
    _CATALOG_CACHE[key] = (mtime, catalog)
    return catalog


def load_catalog_with_annotations(catalog_path: Path) -> dict:
    """Load catalog YAML and merge annotations if they exist.

    Args:
        catalog_path: Path to {source}.yaml or {target}.yaml

    Returns:
        Catalog dict with annotations merged into column descriptions
    """
    if not catalog_path.exists():
        return {}

    # Load base catalog
    with catalog_path.open(encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh) or {}

    # Load corresponding annotations file if it exists
    anno_path = catalog_path.parent / f"{catalog_path.stem}.annotations.yaml"
    if not anno_path.exists():
        return catalog

    with anno_path.open(encoding="utf-8") as fh:
        annotations = yaml.safe_load(fh) or {}

    # Merge annotations into catalog columns
    for schema in catalog.get('schemas', []):
        schema_name = schema.get('name', '')
        for table in schema.get('tables', []):
            table_name = table.get('table_name', '')
            table_key = f"{schema_name}.{table_name}"

            # Skip if no annotations for this table
            if table_key not in annotations.get('annotations', {}):
                continue

            table_anno = annotations['annotations'][table_key]

            # Merge column annotations
            for col in table.get('columns', []):
                col_name = col.get('name', '')
                if col_name not in table_anno.get('columns', {}):
                    continue

                col_anno = table_anno['columns'][col_name]

                # Merge annotations (won't overwrite existing profile data)
                # Annotations take precedence since they're user-maintained
                if col_anno.get('user_description'):
                    col['user_description'] = col_anno['user_description']
                if col_anno.get('mapping_instructions'):
                    col['mapping_instructions'] = col_anno['mapping_instructions']

    return catalog


# ── backend dispatch (catalog_backend flag: 'yaml' default | 'postgres') ────────────────────
#
# Phase 4 of the source-catalog Postgres migration (see
# openspec/changes/migrate-source-catalog-yaml-to-postgres/): these three functions are the
# ONLY place that decides yaml vs postgres. Existing call sites are NOT repointed to them yet
# (that's Phase 6) — this is purely the additive dispatch layer, so default ('yaml') behavior
# is completely unchanged today.

def load_catalog_dispatch(catalog_path: Path, *, kind: str = "source") -> dict:
    """Read dispatch: same shape as :func:`load_catalog_with_annotations` either way."""
    require_reachable(_catalog_backend, "Catalog")
    if _catalog_backend() == "postgres":
        return _pg_load_catalog(catalog_path.stem, kind, catalog_path.parent)
    return load_catalog_with_annotations_cached(catalog_path)


def list_catalog_names_dispatch(catalog_dir: Path, *, kind: str = "source") -> list[str]:
    """List dispatch: which catalog names of *kind* exist, in either backend.

    Mirrors load_catalog_dispatch's branch — the yaml branch is the same glob
    api.routes.catalogs._list_catalog_names always did (unchanged default behavior).
    """
    require_reachable(_catalog_backend, "Catalog")
    if _catalog_backend() == "postgres":
        return _pg_list_source_names(kind)
    return sorted(
        p.stem for p in catalog_dir.glob("*.yaml") if not p.name.endswith(".annotations.yaml")
    )


def save_catalog_dispatch(catalog_path: Path, catalog: dict, *, kind: str = "source") -> None:
    """Write dispatch for a whole-source rebuild (catalog_builder.save_catalog's YAML path,
    or core.catalog_db.save_catalog's Postgres path)."""
    require_reachable(_catalog_backend, "Catalog")
    if _catalog_backend() == "postgres":
        _pg_save_catalog(
            catalog.get("source") or catalog_path.stem, kind=kind,
            connector_type=catalog.get("connector_type"), connection_ref=catalog.get("connection"),
            legal_entity=catalog.get("legal_entity"), version=catalog.get("version"),
            schema_hash=catalog.get("schema_hash"), generated_at=catalog.get("generated_at"),
            schemas=catalog.get("schemas") or [],
        )
        return
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with catalog_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(catalog, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)


def write_table_profile_dispatch(
    catalog_path: Path, schema_name: str, table_name: str, profile: dict,
    *, kind: str = "source", triggered_by: str | None = None,
) -> None:
    """Write dispatch for a single-table profile refresh (discovery.py's
    single-table refresh + bulk rebuild, or core.catalog_db.upsert_table_profile's Postgres
    path) — updates only that table, never rewrites the whole source.

    The YAML branch (:func:`_write_table_profile_yaml`) was moved here from
    api/routes/discovery.py._writeback_table_profile in Phase 6 — a single implementation
    now backs both branches, instead of two copies to keep in sync.
    """
    require_reachable(_catalog_backend, "Catalog")
    if _catalog_backend() == "postgres":
        _pg_upsert_table_profile(
            catalog_path.stem, schema_name, table_name, profile,
            kind=kind, triggered_by=triggered_by,
        )
        return
    _write_table_profile_yaml(catalog_path, schema_name, table_name, profile)


# Table-/column-level keys patched by a profile refresh — everything else (description,
# governance metadata, annotation overlays) is preserved exactly. Moved from
# api/routes/discovery.py in Phase 6.
_PROFILE_STAT_KEYS = {
    "row_count", "primary_key", "inferred_primary_key", "foreign_keys",
    "relations", "inferred_relations", "duplicate_count", "duplicate_pct", "orphan_fk_count",
    "completeness_summary", "pct_columns_described",
}

_COL_STAT_KEYS = {
    "data_type", "null_count", "null_pct", "distinct_count", "uniqueness_pct",
    "min_value", "max_value", "sample_values", "inferred_pattern",
    "pattern_confidence", "placeholder_count", "empty_string_count",
    "invalid_format_count", "type_mismatch_count", "future_date_count",
    "suspicious_date_count", "numeric_outlier_count",
}


def _write_table_profile_yaml(catalog_path: Path, schema_name: str, table_name: str, profile: dict) -> None:
    """Patch the catalog YAML with fresh profiling stats for one table.

    Preserves all non-stat fields (description, governance, annotations, etc.).
    Uses yaml.safe_dump throughout — never yaml.dump.
    """
    if not catalog_path.exists():
        return

    with catalog_path.open(encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh) or {}

    fresh_cols: dict[str, dict] = {
        c["name"]: c for c in profile.get("columns", []) if "name" in c
    }

    matched = False
    for schema in catalog.get("schemas", []):
        if schema.get("name") != schema_name:
            continue
        for tbl in schema.get("tables", []):
            tname = tbl.get("table_name") or tbl.get("name", "")
            if tname != table_name:
                continue
            # Patch table-level stats only
            for key in _PROFILE_STAT_KEYS:
                if key in profile:
                    tbl[key] = profile[key]
            # Patch column-level stats only
            for col in tbl.get("columns", []):
                fc = fresh_cols.get(col.get("name", ""))
                if fc:
                    for key in _COL_STAT_KEYS:
                        if key in fc:
                            col[key] = fc[key]
            matched = True
            break
        if matched:
            break

    if not matched:
        return  # table not found in YAML — don't corrupt the file

    # Update top-level generated_at timestamp
    catalog["generated_at"] = datetime.now().isoformat(timespec="seconds")

    with catalog_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(catalog, fh, default_flow_style=False,
                       sort_keys=False, allow_unicode=True)


