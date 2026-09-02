"""Annotations API routes."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends

from api.deps import get_paths
from api.schemas.annotation import TableAnnotation

router = APIRouter(prefix="/annotations", tags=["annotations"])

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _catalog_dir_for_dataset(dataset: str, paths: dict) -> Path:
    """Find which catalog dir contains this dataset."""
    for kind in ("sources", "targets"):
        if (paths[kind] / f"{dataset}.yaml").exists():
            return paths[kind]
    return paths["sources"]  # default fallback


@router.get("/{dataset}")
async def get_annotations(dataset: str, paths: dict = Depends(get_paths)):
    from core.annotations import load_annotations
    catalog_dir = _catalog_dir_for_dataset(dataset, paths)
    return load_annotations(dataset, catalog_dir)


@router.put("/{dataset}/{table}")
async def set_annotations(
    dataset: str,
    table: str,
    body: TableAnnotation,
    paths: dict = Depends(get_paths),
):
    from core.annotations import load_annotations, save_annotations, set_table_annotations

    catalog_dir = _catalog_dir_for_dataset(dataset, paths)
    annotations = load_annotations(dataset, catalog_dir)

    # Split table key into schema.table
    parts = table.rsplit(".", 1)
    if len(parts) == 2:
        schema_name, table_name = parts
    else:
        schema_name, table_name = "", table

    column_annotations = {
        col_name: {"user_description": col.user_description, "mapping_instructions": col.mapping_instructions}
        for col_name, col in body.columns.items()
    }

    set_table_annotations(
        annotations,
        schema_name,
        table_name,
        user_description=body.user_description,
        mapping_instructions=body.mapping_instructions,
        column_annotations=column_annotations,
    )
    save_annotations(dataset, catalog_dir, annotations)
    return {"status": "saved"}
