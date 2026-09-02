"""Read-only API for governed shared reference sets (Phase 3).

Exposes the seeded/hand-authored reference sets from ``governance/reference_sets.yaml``
so the Asset Workspace can offer them as binding targets and the Reference Dataspace
can browse by set. Sets are read-only through this API.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_reference_set_store, require_read_access
from core.reference_set_store import ReferenceSetStore

router = APIRouter(prefix="/reference-sets", tags=["reference-sets"])


def _summary(reference_set: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": reference_set["id"],
        "name": reference_set["name"],
        "kind": reference_set["kind"],
        "standard_ref": reference_set["standard_ref"],
        "status": reference_set["status"],
        "entry_count": len(reference_set["entries"]),
    }


@router.get("")
async def list_reference_sets(
    store: ReferenceSetStore = Depends(get_reference_set_store),
    _role: str = Depends(require_read_access),
) -> dict[str, Any]:
    """List all governed reference sets (without full entries)."""
    return {"sets": [_summary(s) for s in store.list()]}


@router.get("/{set_id}")
async def get_reference_set(
    set_id: str,
    store: ReferenceSetStore = Depends(get_reference_set_store),
    _role: str = Depends(require_read_access),
) -> dict[str, Any]:
    """Return one reference set including its full entry list."""
    reference_set = store.get(set_id)
    if reference_set is None:
        raise HTTPException(status_code=404, detail=f"Reference set '{set_id}' not found")
    return reference_set
