"""Read-only aggregate API for the Reference Dataspace register (per-code, Postgres).

The register is the published code book: every coded column's PUBLISHED codes
(``in_review`` + ``approved`` only), sourced from the per-code ``reference_code`` store
(Phase 5b.2/5b.3.1). The legacy inline-refdata read (element_state metadata,
candidate/under_review/approved) was dropped in 5b.3.3.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import get_element_state, get_reference_code_repo, get_semantic_type_store, require_read_access
from api.routes.element import _default_business_name
from core.element_state import ElementStateStore
from core.semantic_resolver import normalise_type_id
from core.semantic_type_store import SemanticTypeStore

router = APIRouter(prefix="/reference-data", tags=["reference-data"])

#: Only PUBLISHED per-code statuses appear in the register (frozen code book).
PUBLISHED_STATUSES = ("in_review", "approved")


def _split_key(element_key: str) -> tuple[str, str, str, str] | None:
    """Parse a ``source|schema|table|column`` reference-code element key."""
    parts = element_key.split("|", 3)
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def _field_matches(field: dict[str, Any], query: str | None) -> bool:
    if not query:
        return True
    needle = query.lower()
    terms = [field["business_name"], field["column"]]
    for code in field["codes"]:
        terms.extend([code["code"], code.get("meaning") or ""])
    return any(needle in str(term).lower() for term in terms)


def _build_field(
    *,
    element_key: str,
    codes: list[dict[str, Any]],
    element_state: ElementStateStore,
    semantic_store: SemanticTypeStore,
) -> dict[str, Any] | None:
    """Build a register field from a published codeset (one coded column)."""
    parsed = _split_key(element_key)
    if not parsed:
        return None
    source, schema, table, column = parsed

    record = semantic_store.get(source, schema or None, table, column)
    semantic_type = normalise_type_id(record.get("type_id")) if record else "reference_code"
    stored_name = element_state.get_business_name(source, schema or None, table, column)
    business_name = stored_name or _default_business_name(column)

    out_codes: list[dict[str, Any]] = []
    approved_by: str | None = None
    approved_at: str | None = None
    for code in codes:
        code_status = code.get("status")
        documented = bool(str(code.get("meaning") or "").strip())
        out_codes.append({
            "code": code.get("code"),
            "value": code.get("value"),
            "meaning": code.get("meaning") if documented else None,
            "status": code_status,
            "origin": code.get("origin"),
            "in_source": code.get("origin") == "profiled",
            "share_pct": None,
            "in_list": documented,
        })
        if code_status == "approved" and approved_at is None:
            approved_at = code.get("approved_at")
            approved_by = code.get("approved_by")

    # A codeset is frozen/final only when every published code is approved; if any
    # code is still in_review the whole set is pending sign-off.
    rollup = "in_review" if any(c.get("status") == "in_review" for c in codes) else "approved"
    documented = sum(c["in_list"] for c in out_codes)
    return {
        "source": source,
        "schema": schema,
        "table": table,
        "column": column,
        "business_name": business_name,
        "business_name_is_fallback": not bool(stored_name),
        "semantic_type": semantic_type,
        "status": rollup,
        "code_source": "reference_code",
        "set_kind": "local",
        "bound_set_id": None,
        "codes": out_codes,
        "counts": {
            "total": len(out_codes),
            "documented": documented,
            "approved": sum(1 for c in codes if c.get("status") == "approved"),
            "in_review": sum(1 for c in codes if c.get("status") == "in_review"),
            "rogue": 0,
            "unused": 0,
        },
        "approved_by": approved_by,
        "approved_at": approved_at,
        "asset_link": (
            f"/workspace?source={source}&schema={schema}&table={table}"
            f"&column={column}&tab=refdata"
        ),
    }


@router.get("")
async def get_reference_dataspace(
    source: str | None = None,
    schema: str | None = None,
    status: str | None = Query(default=None),
    semantic_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    reference_code_repo=Depends(get_reference_code_repo),
    _role: str = Depends(require_read_access),
) -> dict[str, Any]:
    """Return the published reference-code register grouped by source, schema, table.

    Every field is a coded column with at least one PUBLISHED code (``in_review`` or
    ``approved``) from the per-code ``reference_code`` store. The field-level status
    rolls up to ``approved`` only when every published code is approved.
    """
    if reference_code_repo is None:
        return {"summary": _summary([]), "sources": []}

    fields: list[dict[str, Any]] = []
    for entry in reference_code_repo.published_register(source):
        field = _build_field(
            element_key=entry["element_key"],
            codes=entry["codes"],
            element_state=element_state,
            semantic_store=semantic_store,
        )
        if not field:
            continue
        if schema and field["schema"] != schema:
            continue
        if status and field["status"] != status:
            continue
        if semantic_type and field["semantic_type"] != normalise_type_id(semantic_type):
            continue
        if _field_matches(field, q):
            fields.append(field)

    return {"summary": _summary(fields), "sources": _group_fields(fields)}


def _summary(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_fields": len(fields),
        "status_counts": {
            status: sum(field["status"] == status for field in fields)
            for status in PUBLISHED_STATUSES
        },
        "gaps": 0,
        "approved_codes": sum(field["counts"]["approved"] for field in fields),
        "in_review_codes": sum(field["counts"]["in_review"] for field in fields),
        "codes_of_record": sum(field["counts"]["approved"] for field in fields),
    }


def _group_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for field in fields:
        grouped[field["source"]][field["schema"]][field["table"]].append(field)
    return [
        {
            "source": source,
            "schemas": [
                {
                    "schema": schema,
                    "tables": [
                        {"table": table, "fields": sorted(table_fields, key=lambda field: field["column"])}
                        for table, table_fields in sorted(tables.items())
                    ],
                }
                for schema, tables in sorted(schemas.items())
            ],
        }
        for source, schemas in sorted(grouped.items())
    ]