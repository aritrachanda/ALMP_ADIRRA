"""
annotations.py  –  Load / save the catalog annotation overlay.

Postgres-backed (govern-pg-e/f-annotations): ``load_annotations``/``save_annotations`` delegate
to ``core.annotation_repo.AnnotationRepo`` — the legacy YAML branch (one ``<dataset>.
annotations.yaml`` file per dataset) was retired in Slice F once ``annotation_backend`` had been
live on Postgres and stable; the old files are archived, not deleted (see
``docs/governance-postgres-migration.md``). The two pure helper functions below
(``get_table_annotations``/``set_table_annotations``) are plain dict manipulation with no I/O and
are unaffected by that retirement.
"""
from __future__ import annotations

from pathlib import Path


def load_annotations(dataset_name: str, catalog_dir: Path | None = None) -> dict:
    """Load annotations for *dataset_name*.

    *catalog_dir* is accepted (and ignored) for call-site compatibility with the pre-Postgres
    signature — every caller still passes it.
    """
    from core.annotation_repo import AnnotationRepo
    return AnnotationRepo().load(dataset_name)


def save_annotations(dataset_name: str, catalog_dir: Path | None, data: dict) -> None:
    """Save annotations for *dataset_name*. *catalog_dir* is accepted (and ignored) for
    call-site compatibility -- nothing is written to disk anymore."""
    data.setdefault("version", 1)
    data.setdefault("dataset", dataset_name)
    data.setdefault("annotations", {})

    from core.annotation_repo import AnnotationRepo
    AnnotationRepo().save(dataset_name, data)


def get_table_annotations(annotations: dict, schema_name: str, table_name: str) -> dict:
    """Get annotations for a specific table.

    Returns dict with keys: user_description, mapping_instructions, columns.
    """
    key = f"{schema_name}.{table_name}"
    table_ann = annotations.get("annotations", {}).get(key, {})
    return {
        "user_description": table_ann.get("user_description") or "",
        "mapping_instructions": table_ann.get("mapping_instructions") or "",
        "columns": table_ann.get("columns", {}),
    }


def set_table_annotations(
    annotations: dict,
    schema_name: str,
    table_name: str,
    user_description: str | None,
    mapping_instructions: str | None,
    column_annotations: dict[str, dict[str, str | None]],
) -> None:
    """Update annotations for a specific table in-place.

    *column_annotations* is ``{col_name: {"user_description": ..., "mapping_instructions": ...}}``.
    """
    key = f"{schema_name}.{table_name}"
    ann = annotations.setdefault("annotations", {})

    table_entry: dict = {}
    if user_description:
        table_entry["user_description"] = user_description
    if mapping_instructions:
        table_entry["mapping_instructions"] = mapping_instructions

    cols: dict = {}
    for col_name, col_data in column_annotations.items():
        col_entry = {}
        ud = col_data.get("user_description")
        mi = col_data.get("mapping_instructions")
        if ud:
            col_entry["user_description"] = ud
        if mi:
            col_entry["mapping_instructions"] = mi
        if col_entry:
            cols[col_name] = col_entry
    if cols:
        table_entry["columns"] = cols

    if table_entry:
        ann[key] = table_entry
    elif key in ann:
        del ann[key]
