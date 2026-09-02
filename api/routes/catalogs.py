"""Catalog API routes."""
from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_paths
from core.catalog import list_catalog_names_dispatch, load_catalog_dispatch

router = APIRouter(prefix="/catalogs", tags=["catalogs"])

CatalogType = Literal["sources", "targets"]

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _catalog_dir(paths: dict[str, Path], catalog_type: CatalogType) -> Path:
    return paths[catalog_type]


def _list_catalog_names(catalog_dir: Path, kind: str = "source") -> list[str]:
    return list_catalog_names_dispatch(catalog_dir, kind=kind)


def _load_catalog_yaml(catalog_dir: Path, name: str, kind: str = "source") -> dict:
    path = catalog_dir / f"{name}.yaml"
    # Respects catalog_backend (Phase 6); shared mtime-cached loader in yaml mode.
    # In postgres mode there's no on-disk file to check — load_catalog_dispatch
    # returns {} for a missing/unknown source, which we translate to 404 below.
    catalog = load_catalog_dispatch(path, kind=kind)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"Catalog '{name}' not found")
    return catalog


@router.get("/{type}")
async def list_catalogs(type: CatalogType, paths: dict = Depends(get_paths)):
    kind = "source" if type == "sources" else "target"
    names = _list_catalog_names(_catalog_dir(paths, type), kind)
    return {"type": type, "catalogs": [{"name": n} for n in names]}


@router.get("/{type}/{name}")
async def get_catalog(type: CatalogType, name: str, paths: dict = Depends(get_paths)):
    kind = "source" if type == "sources" else "target"
    return _load_catalog_yaml(_catalog_dir(paths, type), name, kind)


@router.get("/{type}/{name}/{table}")
async def get_table(type: CatalogType, name: str, table: str, paths: dict = Depends(get_paths)):
    kind = "source" if type == "sources" else "target"
    catalog = _load_catalog_yaml(_catalog_dir(paths, type), name, kind)
    for schema in catalog.get("schemas", []):
        for tbl in schema.get("tables", []):
            if tbl.get("table_name") == table:
                return tbl
    raise HTTPException(status_code=404, detail=f"Table '{table}' not found in catalog '{name}'")


class AIGenerateRequest(BaseModel):
    field: str = "user_description"
    column_name: str | None = None
    user_instructions: str = ""


@router.post("/{type}/{name}/{table}/ai-generate")
async def ai_generate(
    type: CatalogType,
    name: str,
    table: str,
    body: AIGenerateRequest,
    paths: dict = Depends(get_paths),
):
    kind = "source" if type == "sources" else "target"
    catalog = _load_catalog_yaml(_catalog_dir(paths, type), name, kind)
    tbl = None
    for schema in catalog.get("schemas", []):
        for t in schema.get("tables", []):
            if t.get("table_name") == table:
                tbl = t
                break
    if tbl is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found")

    from agents.catalog_agent import generate_descriptions

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        partial(
            generate_descriptions,
            tbl,
            field=body.field,
            column_name=body.column_name,
            user_instructions=body.user_instructions,
        ),
    )
    return results
