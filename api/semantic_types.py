"""Semantic type API — governed type resolution and steward disposition."""
from __future__ import annotations

import asyncio
import json as _json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import get_audit_store, get_element_state, get_paths, get_project, get_semantic_type_store
from api.llm_errors import format_llm_error
from core.audit import AuditStore
from core.audit import events as audit_events
from core.catalog import load_catalog_dispatch
from core.element_state import ElementStateStore
from core.governance_events import emit as emit_governance_event
from core.semantic_resolver import (
    ColumnProgressStatus,
    ResolverConfig,
    SemanticResolver,
    domain_role_for_type,
    get_vocabulary_structure,
)
from core.semantic_type_store import SemanticTypeStore

router = APIRouter(prefix="/semantic-types", tags=["semantic-types"])

_ROOT = Path(__file__).resolve().parent.parent


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Events frame (event name + JSON data)."""
    return f"event: {event}\ndata: {_json.dumps(data, default=str)}\n\n"


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _glossary_term_for(source: str, schema: str, table: str, column: str) -> dict | None:
    """Return the linked glossary term (as text + provenance) for a column, or
    None. Mirrors the flat-`terms` related_objects lookup used elsewhere; only
    approved/confirmed links count. Used to feed the LLM residual payload."""
    from core.glossary_db.read_api import glossary_terms
    from core.glossary_db.status import CONFIRMED_STATUSES
    candidates = {
        f"source|{source}|{schema}.{table}.{column}",
        f"source|{source}|{table}.{column}",
    }
    for term in glossary_terms():
        if candidates & set(term.get("related_objects") or []):
            if term.get("status") not in CONFIRMED_STATUSES:
                return None
            ai_fields = set(term.get("ai_generated_fields") or [])
            # Term counts as human unless its core meaning fields are AI-drafted.
            provenance = "ai" if ({"business_description", "detailed_description"} & ai_fields) else "human"
            return {
                "title": term.get("title"),
                "description": term.get("business_description") or term.get("detailed_description") or "",
                "synonyms": term.get("synonyms") or [],
                "provenance": provenance,
            }
    return None


def _build_governance_context(
    source: str,
    schema: str,
    table: str,
    table_dict: dict,
    element_state: ElementStateStore,
) -> dict[str, dict[str, Any]]:
    """Assemble the per-column governance trio (Definition + Business Name +
    Glossary term), each provenance-tagged (human vs ai), for the LLM residual
    payload. Only human-meaningful fields are included."""
    ctx: dict[str, dict[str, Any]] = {}
    for col in table_dict.get("columns", []) or []:
        name = col.get("name")
        if not name:
            continue
        entry: dict[str, Any] = {}
        meta = element_state.get_metadata(source, schema, table, name) or {}

        business_name = element_state.get_business_name(source, schema, table, name)
        if business_name:
            entry["business_name"] = {
                "text": business_name,
                "provenance": "ai" if meta.get("business_name_is_ai") else "human",
            }

        definition = element_state.get_description(source, schema, table, name)
        if definition and definition.strip():
            entry["definition"] = {
                "text": definition.strip(),
                "provenance": "ai" if meta.get("is_ai_generated") else "human",
            }

        glossary = _glossary_term_for(source, schema, table, name)
        if glossary:
            entry["glossary"] = glossary

        if entry:
            ctx[name] = entry
    return ctx


class ResolveRequest(BaseModel):
    include_ai: bool = False


class AcceptRequest(BaseModel):
    type_id: str | None = None
    domain_role: str | None = None
    accepted_by: str | None = None
    accepted_by_role: str | None = None
    rationale: str | None = None
    ai_assisted: bool = False


class SubmitRequest(BaseModel):
    submitted_by: str | None = None


# Parsed source catalogs are cached by on-disk mtime (catalog + annotations overlay).
# Without this, every /semantic-types call re-parsed the whole source catalog YAML
# (measured ~6s for a 3.5MB catalog) — the element endpoint already caches the same way.
_CATALOG_CACHE: dict[str, dict[str, Any]] = {}
_CATALOG_CACHE_MTIME: dict[str, float] = {}


def _load_source_catalog(sources_dir: Path, source: str) -> dict[str, Any]:
    path = sources_dir / f"{source}.yaml"
    if not path.exists():
        # No on-disk file to cache by mtime (e.g. postgres-backed catalog with no
        # legacy YAML left over) — dispatch directly every call. load_catalog_dispatch's
        # postgres branch has no cache of its own either, matching element.py/insights.py.
        catalog = load_catalog_dispatch(path)
        if not catalog:
            raise HTTPException(status_code=404, detail=f"Source catalog '{source}' not found")
        return catalog
    mtime = path.stat().st_mtime
    anno_path = path.parent / f"{path.stem}.annotations.yaml"
    if anno_path.exists():
        mtime = max(mtime, anno_path.stat().st_mtime)
    if source in _CATALOG_CACHE and _CATALOG_CACHE_MTIME.get(source) == mtime:
        return _CATALOG_CACHE[source]
    catalog = load_catalog_dispatch(path)
    _CATALOG_CACHE[source] = catalog
    _CATALOG_CACHE_MTIME[source] = mtime
    return catalog


def _find_table(catalog: dict[str, Any], table: str, schema: str | None = None) -> tuple[str, dict[str, Any]]:
    for sc in catalog.get("schemas", []) or []:
        schema_name = sc.get("name") or ""
        if schema and schema_name != schema:
            continue
        for tbl in sc.get("tables", []) or []:
            if tbl.get("table_name") == table:
                return schema_name, tbl
    raise HTTPException(status_code=404, detail=f"Table '{table}' not found")


def _table_records(
    *,
    store: SemanticTypeStore,
    source: str,
    schema: str | None,
    table: str,
    table_dict: dict[str, Any],
) -> list[dict[str, Any]]:
    records = []
    for column in table_dict.get("columns", []) or []:
        records.append(store.get_or_default(source, schema, table, column.get("name") or ""))
    return records


def _audit_subject(source: str, schema: str | None, table: str, column: str | None = None) -> str:
    base = f"{source}:{schema or ''}.{table}"
    return f"{base}.{column}" if column else base


@router.get("/vocabulary")
async def get_semantic_vocabulary():
    """Return the governed vocabulary structure for UI dropdowns."""
    return get_vocabulary_structure()


# Human-readable meaning of each AI sample policy (D5), shown in the panel.
_SAMPLE_POLICY_MEANINGS: dict[str, str] = {
    "full": "Raw sample values are sent to the LLM unchanged.",
    "masked": "Raw sample values are redacted before leaving for the LLM; counts, "
              "stats and shape metrics are kept.",
    "stats_only": "Sample values are dropped entirely; only counts, stats and shape "
                  "metrics are sent.",
}

# The standing propose-only rules the panel makes legible (§C3 / invariants).
_AI_GOVERNANCE_RULES: list[str] = [
    "AI proposes, the steward decides — an AI draft never auto-approves.",
    "AI never accepts — its output is capped at proposed/suggested.",
    "AI output never enters a score — the deterministic resolver is authoritative.",
    "Fail-safe empty — any provider or parse error yields no draft, leaving the "
    "deterministic result unaffected.",
    "Output is constrained to the closed governed vocabulary.",
]


@router.get("/ai-governance")
async def get_ai_governance(project: dict = Depends(get_project)):
    """Return the active AI policy for the read-only AI-governance panel (U5c / D5).

    Client-facing transparency: bank data leaving for an LLM is a contractual
    matter, so the policy must be legible. Read-only this phase — role-gated
    editing is deferred until ADIRRA has an auth/role model (the seam is labelled).
    """
    agent_cfg = project.get("agent", {}) if isinstance(project, dict) else {}
    policy = str(agent_cfg.get("ai_sample_policy", "masked")).lower()
    if policy not in _SAMPLE_POLICY_MEANINGS:
        policy = "masked"
    return {
        "ai_sample_policy": policy,
        "ai_sample_policy_meaning": _SAMPLE_POLICY_MEANINGS[policy],
        "ai_sample_policy_options": [
            {"value": key, "meaning": meaning}
            for key, meaning in _SAMPLE_POLICY_MEANINGS.items()
        ],
        "provider": agent_cfg.get("provider"),
        "model": agent_cfg.get("model"),
        "rules": _AI_GOVERNANCE_RULES,
        "read_only": True,
        "edit_seam": "editable by [role] — coming with roles",
    }



@router.get("/{source}/all")
async def get_all_semantic_types_for_source(
    source: str,
    store: SemanticTypeStore = Depends(get_semantic_type_store),
):
    """Return all semantic type records for a source."""
    records = store.find_in_source(source)
    return {"source": source, "items": records}


@router.get("/{source}/{table}")
async def get_semantic_types(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
):
    catalog = _load_source_catalog(paths["sources"], source)
    resolved_schema, table_dict = _find_table(catalog, table, schema)
    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "columns": _table_records(
            store=store, source=source, schema=resolved_schema, table=table, table_dict=table_dict
        ),
    }


@router.post("/{source}/{table}/resolve")
async def resolve_semantic_types(
    source: str,
    table: str,
    body: ResolveRequest | None = None,
    schema: Optional[str] = Query(default=None),
    dry_run: bool = Query(default=False),
    paths: dict = Depends(get_paths),
    project: dict = Depends(get_project),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
    element_state: ElementStateStore = Depends(get_element_state),
):
    catalog = _load_source_catalog(paths["sources"], source)
    resolved_schema, table_dict = _find_table(catalog, table, schema)

    if dry_run:
        # U1a preview: resolve with evidence widening forced ON, persist nothing,
        # and return the diff vs the currently persisted records. No audit, no writes.
        preview_resolver = SemanticResolver(
            store=store,
            config=ResolverConfig.from_project(project),
            evidence_widening_override=True,
        )
        preview = preview_resolver.resolve_table(
            source=source,
            schema=resolved_schema,
            table=table_dict,
            include_ai=False,
            persist=False,
        )
        changes: list[dict[str, Any]] = []
        for proposed in preview["columns"]:
            column_name = str(proposed.get("key", "")).split("|")[-1]
            current = store.get(source, resolved_schema, table, column_name) or {}
            fields = ("type_id", "confidence")
            if any(proposed.get(f) != current.get(f) for f in fields):
                changes.append({
                    "key": proposed.get("key"),
                    "column": column_name,
                    "current": {f: current.get(f) for f in fields},
                    "proposed": {f: proposed.get(f) for f in fields},
                    "resolution_reason": proposed.get("resolution_reason"),
                    "nearest_candidates": proposed.get("nearest_candidates"),
                    "evidence": proposed.get("evidence"),
                })
        return {
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "dry_run": True,
            "evidence_widening": True,
            "changed_count": len(changes),
            "column_count": len(preview["columns"]),
            "changes": changes,
        }

    resolver = SemanticResolver(store=store, config=ResolverConfig.from_project(project))
    include_ai = bool(body.include_ai if body else False)
    # Provenance-tagged trio (Definition + Business Name + Glossary term) for the
    # LLM residual payload — only built when the LLM will actually run.
    governance_context = (
        _build_governance_context(source, resolved_schema, table, table_dict, element_state)
        if include_ai else None
    )
    try:
        result = resolver.resolve_table(
            source=source,
            schema=resolved_schema,
            table=table_dict,
            include_ai=include_ai,
            persist=True,
            governance_context=governance_context,
        )
    except Exception as exc:  # noqa: BLE001 — surface the LLM residual failure as a banner payload
        if not include_ai:
            raise  # deterministic resolve never hits the LLM; keep its original behaviour
        return {
            "source": source, "schema": resolved_schema, "table": table,
            "columns": [], "findings": [], "error": format_llm_error(exc),
        }
    audit_store.log_business(
        event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
        subject_type="table",
        subject_id=_audit_subject(source, resolved_schema, table),
        payload={
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "include_ai": bool(body.include_ai if body else False),
            "column_count": len(result["columns"]),
            "finding_count": len(result["findings"]),
        },
    )
    emit_governance_event(
        audit_events.SEMANTIC_TYPES_RESOLVED,
        {
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "column_count": len(result["columns"]),
            "finding_count": len(result["findings"]),
        },
    )
    return {"source": source, "schema": resolved_schema, "table": table, **result}


@router.post("/{source}/resolve-all")
async def resolve_all_semantic_types(
    source: str,
    paths: dict = Depends(get_paths),
    project: dict = Depends(get_project),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Re-resolve semantic types for *every* table in a source.

    Opt-in companion to a source-level profile rebuild: once the underlying
    facts are refreshed, this re-derives types for the non-accepted fields so
    the deductions stay in step with the data. Steward decisions are safe —
    ``resolve_table`` never overwrites an accepted record; only unaccepted
    (still machine-proposed or unresolved) ones are re-derived. Deterministic
    only (no LLM).
    """
    catalog = _load_source_catalog(paths["sources"], source)
    resolver = SemanticResolver(store=store, config=ResolverConfig.from_project(project))

    table_count = 0
    column_count = 0
    for schema in catalog.get("schemas", []):
        schema_name = schema.get("name", "")
        for table_dict in schema.get("tables", []):
            table_name = table_dict.get("table_name") or table_dict.get("name", "")
            if not table_name:
                continue
            result = resolver.resolve_table(
                source=source,
                schema=schema_name,
                table=table_dict,
                include_ai=False,
                persist=True,
            )
            table_count += 1
            column_count += len(result["columns"])

    audit_store.log_business(
        event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
        subject_type="source",
        subject_id=source,
        payload={
            "source": source,
            "scope": "source",
            "table_count": table_count,
            "column_count": column_count,
        },
    )
    emit_governance_event(
        audit_events.SEMANTIC_TYPES_RESOLVED,
        {
            "source": source,
            "scope": "source",
            "table_count": table_count,
            "column_count": column_count,
        },
    )
    return {"source": source, "table_count": table_count, "column_count": column_count}


@router.post("/{source}/{table}/resolve-stream")
async def resolve_semantic_types_stream(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    project: dict = Depends(get_project),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Re-resolve one table's semantic types, streaming per-column progress via SSE.

    Deterministic companion to Refresh Profile: non-accepted fields are re-derived
    from the fresh facts while accepted decisions are preserved
    (no LLM). Emits ``started``, one ``column`` frame per column as it is worked,
    ``done`` on success, or ``error`` if resolution fails.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    resolved_schema, table_dict = _find_table(catalog, table, schema)
    resolver = SemanticResolver(store=store, config=ResolverConfig.from_project(project))

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        columns = table_dict.get("columns", []) or []
        yield _sse("started", {
            "source": source, "schema": resolved_schema, "table": table,
            "total": len(columns),
        })

        def progress_cb(index: int, total: int, column_name: str, status: ColumnProgressStatus) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("column", {
                "index": index, "total": total, "column": column_name,
                "table": table, "schema": resolved_schema,
            }))

        def work():
            try:
                result = resolver.resolve_table(
                    source=source, schema=resolved_schema, table=table_dict,
                    include_ai=False, persist=True, progress_cb=progress_cb,
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("__result__", result))
            except Exception as exc:  # pragma: no cover - surfaced as SSE error
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", str(exc)))

        fut = loop.run_in_executor(None, work)
        result: dict | None = None
        error: str | None = None
        while True:
            kind, data = await queue.get()
            if kind == "__result__":
                result = data
                break
            if kind == "__error__":
                error = data
                break
            yield _sse(kind, data)
        await fut

        if error is not None or result is None:
            yield _sse("error", {"message": error or "Resolution failed"})
            return

        audit_store.log_business(
            event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
            subject_type="table",
            subject_id=_audit_subject(source, resolved_schema, table),
            payload={
                "source": source, "schema": resolved_schema, "table": table,
                "include_ai": False, "column_count": len(result["columns"]),
                "finding_count": len(result["findings"]),
            },
        )
        emit_governance_event(
            audit_events.SEMANTIC_TYPES_RESOLVED,
            {
                "source": source, "schema": resolved_schema, "table": table,
                "column_count": len(result["columns"]),
                "finding_count": len(result["findings"]),
            },
        )
        yield _sse("done", {
            "source": source, "schema": resolved_schema, "table": table,
            "column_count": len(result["columns"]),
            "finding_count": len(result["findings"]),
        })

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{source}/resolve-all-stream")
async def resolve_all_semantic_types_stream(
    source: str,
    paths: dict = Depends(get_paths),
    project: dict = Depends(get_project),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Re-resolve every table in a source, streaming per-column progress via SSE.

    Source-level companion to Rebuild all profiles. Same steward-safe, deterministic
    behaviour as the single-table stream; ``column`` frames carry the table they
    belong to so the UI can show exactly what is being worked.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    resolver = SemanticResolver(store=store, config=ResolverConfig.from_project(project))

    all_tables: list[tuple[str, str, dict]] = []
    for schema in catalog.get("schemas", []):
        schema_name = schema.get("name", "")
        for table_dict in schema.get("tables", []):
            table_name = table_dict.get("table_name") or table_dict.get("name", "")
            if table_name:
                all_tables.append((schema_name, table_name, table_dict))
    column_total = sum(len(t[2].get("columns", []) or []) for t in all_tables)

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        yield _sse("started", {
            "source": source, "table_count": len(all_tables), "column_total": column_total,
        })

        def work():
            done_columns = 0
            table_count = 0
            column_count = 0
            try:
                for schema_name, table_name, table_dict in all_tables:
                    def progress_cb(index: int, total: int, column_name: str, status: ColumnProgressStatus,
                                    _schema=schema_name, _table=table_name):
                        nonlocal done_columns
                        done_columns += 1
                        loop.call_soon_threadsafe(queue.put_nowait, ("column", {
                            "column": column_name, "table": _table, "schema": _schema,
                            "index": done_columns, "total": column_total,
                            "table_index": index, "table_total": total,
                        }))

                    result = resolver.resolve_table(
                        source=source, schema=schema_name, table=table_dict,
                        include_ai=False, persist=True, progress_cb=progress_cb,
                    )
                    table_count += 1
                    column_count += len(result["columns"])
                loop.call_soon_threadsafe(queue.put_nowait, (
                    "__result__", {"table_count": table_count, "column_count": column_count},
                ))
            except Exception as exc:  # pragma: no cover - surfaced as SSE error
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", str(exc)))

        fut = loop.run_in_executor(None, work)
        result: dict | None = None
        error: str | None = None
        while True:
            kind, data = await queue.get()
            if kind == "__result__":
                result = data
                break
            if kind == "__error__":
                error = data
                break
            yield _sse(kind, data)
        await fut

        if error is not None or result is None:
            yield _sse("error", {"message": error or "Resolution failed"})
            return

        audit_store.log_business(
            event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
            subject_type="source",
            subject_id=source,
            payload={
                "source": source, "scope": "source",
                "table_count": result["table_count"], "column_count": result["column_count"],
            },
        )
        emit_governance_event(
            audit_events.SEMANTIC_TYPES_RESOLVED,
            {
                "source": source, "scope": "source",
                "table_count": result["table_count"], "column_count": result["column_count"],
            },
        )
        yield _sse("done", {
            "source": source,
            "table_count": result["table_count"], "column_count": result["column_count"],
        })

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{source}/{table}/{column}/accept")
async def accept_semantic_type(
    source: str,
    table: str,
    column: str,
    body: AcceptRequest | None = None,
    schema: Optional[str] = Query(default=None),
    store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    payload = body or AcceptRequest()
    prior = store.get(source, schema, table, column)
    prior_type = (prior or {}).get("type_id")
    # Keep type and domain in sync: when the steward overrides the type but sends no
    # domain, derive the canonical domain from the vocabulary so an overridden
    # 'natural_key' never keeps a stale 'surrogate_id' (and vice-versa).
    domain_role = payload.domain_role
    if payload.type_id and not domain_role:
        domain_role = domain_role_for_type(payload.type_id)
    try:
        record = store.accept(
            source,
            schema,
            table,
            column,
            accepted_by=payload.accepted_by,
            accepted_by_role=payload.accepted_by_role,
            type_id=payload.type_id,
            domain_role=domain_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_store.log_business(
        event_type=audit_events.SEMANTIC_TYPE_ACCEPTED,
        subject_type="column",
        subject_id=_audit_subject(source, schema, table, column),
        payload={
            "source": source,
            "schema": schema,
            "table": table,
            "column": column,
            "type_id": record.get("type_id"),
            "prior_type_id": prior_type,
            "overridden": bool(payload.type_id and payload.type_id != prior_type),
            "rationale": payload.rationale,
            "ai_assisted": bool(payload.ai_assisted),
        },
    )
    emit_governance_event(
        audit_events.SEMANTIC_TYPE_ACCEPTED,
        {
            "source": source,
            "schema": schema,
            "table": table,
            "column": column,
            "type_id": record.get("type_id"),
            "prior_type_id": prior_type,
        },
    )
    return record


# SD-R3b: the /submit (submit-for-review) and /queue endpoints were removed —
# Semantic Type is an analyst annotation, not a steward-queue governance artifact.
# The store.submit_for_review / get_pending_review methods and the SEMANTIC_TYPE_SUBMITTED
# audit constant were fully removed (2026-08-18) once confirmed to have no live caller —
# submission time/actor for the whole Interpretation Set belongs to the lifecycle system.


