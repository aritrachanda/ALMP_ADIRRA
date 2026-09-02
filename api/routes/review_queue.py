"""Review queue API — unified governance pending-review queue.

GET /review-queue/{source}
    Returns all items that have been explicitly submitted for steward review
    and are awaiting a decision, across both the definition (ElementStateStore)
    and semantic-type (SemanticTypeStore) governance tracks.

Each item includes:
  - aspect_type: "definition" | "semantic_type"
  - provenance:  "human_authored" | "ai_detected" | "rule_based"
  - bulk_eligible: True when the semantic type is Tier-1 (high confidence,
                   validator-confirmed) and so can be bulk-approved
  - preview: short summary text for display in the steward queue UI
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.deps import (
    get_element_state,
    get_reference_binding_review_repo,
    get_reference_code_repo,
    get_reference_set_store,
)
from core.element_state import ElementStateStore
from core.reference_code_repo import ReferenceCodeRepo
from core.reference_set_store import ReferenceSetStore

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


# SD-R3b: Semantic Type left the steward Review Workspace — it is an analyst
# annotation in the Definition tab now, and the DQ score already tracks
# classification completeness. Only definition items are queued for review.


def _definition_items(
    element_state: ElementStateStore, source: str
) -> list[dict[str, Any]]:
    """Map pending-review definition items to the unified queue shape."""
    items = []
    for item in element_state.get_pending_review(source):
        desc = item.get("description") or ""
        preview = (desc[:80] + "…") if len(desc) > 80 else desc
        items.append({
            "key": item["key"],
            "source": item["source"],
            "schema": item["schema"],
            "table": item["table"],
            "column": item["column"],
            "aspect_type": "definition",
            "submitted_at": item["submitted_at"],
            "submitted_by": item["submitted_by"],
            "provenance": item["provenance"],
            "bulk_eligible": False,
            "preview": preview,
            "lifecycle_state": item["state"],
            # Semantic-type fields not applicable
            "semantic_type_id": None,
            "confidence": None,
            "tier": None,
        })
    return items


@router.get("/{source}")
async def get_review_queue(
    source: str,
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Return all pending governance review items for a source.

    Items are returned in submission order (earliest first) and split by
    ``aspect_type``.  The caller can further filter by ``aspect_type`` or
    sort by any field — no server-side filtering is applied here.
    """
    definition_items = _definition_items(element_state, source)
    definition_items.sort(key=lambda x: x.get("submitted_at") or "")

    return {
        "source": source,
        "total": len(definition_items),
        "definition_count": len(definition_items),
        "semantic_type_count": 0,
        "items": definition_items,
    }


@router.get("/{source}/reference-codes")
async def get_reference_code_queue(
    source: str,
    element_state: ElementStateStore = Depends(get_element_state),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_set_store: ReferenceSetStore = Depends(get_reference_set_store),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Pending reference codesets + bound-field binding decisions for a source (steward lane).

    One item per column with ≥1 ``in_review`` code OR ≥1 active tombstone (withdrawn/revoked),
    PLUS one item per bound column whose binding decision has itself been submitted for review
    (2026-08-16 redesign) — rendered as a plain "Bound to <set name>" statement, never a
    per-code list, since a bound field's recognised codes are governed by the master list, not
    individually authored. Shaped like the unified queue item so the Review Workspace can
    render both kinds alongside the rest.
    """
    items: list[dict[str, Any]] = []
    for cs in reference_code_repo.pending_codesets(source):
        n, t = cs["in_review_count"], cs["tombstone_count"]
        preview = f"{n} code{'' if n == 1 else 's'} in review"
        if t:
            preview += f" · {t} withdrawn/revoked"
        items.append({
            "key": f"{cs['key']}|rc",
            "source": cs["source"], "schema": cs["schema"],
            "table": cs["table"], "column": cs["column"],
            "aspect_type": "reference_data",
            "submitted_at": cs["submitted_at"] or "",
            "submitted_by": None,
            "provenance": "human_authored",
            "bulk_eligible": False,
            "preview": preview,
            "lifecycle_state": "in_review" if n else "tombstone",
            "in_review_count": n,
            "tombstone_count": t,
            "semantic_type_id": None, "confidence": None, "tier": None,
        })

    for pend in reference_binding_review_repo.pending_review(source):
        key = pend["key"]
        set_id = element_state.get_reference_binding(
            pend["source"], pend["schema"], pend["table"], pend["column"]
        )
        set_info = reference_set_store.get(set_id) if set_id else None
        set_name = set_info["name"] if set_info else (set_id or "a reference set")
        review = reference_binding_review_repo.get_review(key)
        items.append({
            "key": f"{key}|rb",
            "source": pend["source"], "schema": pend["schema"],
            "table": pend["table"], "column": pend["column"],
            "aspect_type": "reference_binding",
            "submitted_at": review["submitted_at"] or "",
            "submitted_by": review["submitted_by"],
            "provenance": "human_authored",
            "bulk_eligible": False,
            "preview": f"Bound to {set_name}",
            "lifecycle_state": pend["state"],
            "bound_set_id": set_id,
            "bound_set_name": set_name,
            "semantic_type_id": None, "confidence": None, "tier": None,
        })

    items.sort(key=lambda x: x.get("submitted_at") or "")
    return {"source": source, "total": len(items), "items": items}
