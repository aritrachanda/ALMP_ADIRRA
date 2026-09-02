"""Discovery API routes — table stats, ad-hoc queries, and scoped chat."""
from __future__ import annotations

import asyncio
import json as _json
import logging
import sys
import time
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import (
    get_agent_config, get_audit_store, get_connections, get_dq_service, get_paths, get_project,
    get_semantic_type_store,
)
from api.schemas.discovery import QueryRequest
from core.audit import AuditStore
from core.audit import events as audit_events
from core.catalog import load_catalog_dispatch, write_table_profile_dispatch
from core.governance_events import emit as emit_governance_event
from core.semantic_resolver import ResolverConfig, SemanticResolver
from core.semantic_type_store import SemanticTypeStore
import core.extractors.profiler as profiler

router = APIRouter(prefix="/discovery", tags=["discovery"])
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_catalog_yaml(catalog_dir: Path, name: str) -> dict:
    path = catalog_dir / f"{name}.yaml"
    # Respects catalog_backend (Phase 6) — in postgres mode there's no on-disk file to
    # gate on, so 404 is decided from the dispatched result, not path.exists().
    catalog = load_catalog_dispatch(path)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"Dataset '{name}' not found")
    return catalog


@router.get("/datasets")
async def list_datasets(
    project: dict = Depends(get_project),
):
    """List all discoverable datasets (sources only). Targets (e.g., BIRD/CRDM) are excluded from Discovery."""
    items = []
    for src in project.get("sources", []):
        items.append({"name": src["name"], "kind": "source"})
    return items


@router.get("/{dataset}/{table}/stats")
async def table_stats(
    dataset: str,
    table: str,
    paths: dict = Depends(get_paths),
):
    # Allow schema-qualified table names like 'schema.table' to disambiguate
    schema_part = None
    table_part = table
    if "." in table:
        schema_part, table_part = table.split('.', 1)

    # Only search sources for discovery (exclude targets)
    for kind in ("sources",):
        cat_dir = paths[kind]
        catalog = _load_catalog_yaml(cat_dir, dataset)
        for schema in catalog.get("schemas", []):
            schema_name = schema.get("name") or schema.get("schema_name")
            for tbl in schema.get("tables", []):
                if schema_part:
                    if (schema_name == schema_part) and (tbl.get("table_name") == table_part):
                        return tbl
                else:
                    if tbl.get("table_name") == table:
                        return tbl
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{dataset}'")
    raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")


@router.post("/{dataset}/{table}/query")
async def run_query(
    dataset: str,
    table: str,
    body: QueryRequest,
    connections: dict = Depends(get_connections),
    project: dict = Depends(get_project),
):
    from core.connectors import load_connector

    # Find connection config for this dataset (sources only)
    conn_name = None
    for src in project.get("sources", []):
        if src["name"] == dataset:
            conn_name = src.get("connection", dataset)
            break
    if not conn_name:
        raise HTTPException(status_code=404, detail=f"No connection for dataset '{dataset}'")

    conn_cfg = None
    for c in connections.get("connections", []):
        if c.get("name") == conn_name:
            conn_cfg = c
            break
    if not conn_cfg:
        raise HTTPException(status_code=404, detail=f"Connection '{conn_name}' not found")

    # Execute read-only query with limit
    sql = body.sql.strip().rstrip(";")
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    limited_sql = f"SELECT * FROM ({sql}) AS _q LIMIT {body.limit}"

    connector = load_connector(conn_cfg)
    try:
        connector.connect()
        rows = connector.execute(limited_sql)
        # Get column names from cursor description if available
        columns = [f"col_{i}" for i in range(len(rows[0]))] if rows else []
        return {
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows],
            "row_count": len(rows),
        }
    finally:
        connector.close()


def _compute_table_profile(
    dataset: str,
    table: str,
    paths: dict,
    connections: dict,
    project: dict,
) -> dict:
    """Resolve a table from catalogs and compute its on-demand profile.

    Returns the table-shaped profile dict (the same payload served by the
    ``/profile`` endpoint). Raises ``HTTPException`` on resolution failures.
    """
    # Support schema-qualified table names like 'schema.table'
    schema_part = None
    table_part = table
    if "." in table:
        schema_part, table_part = table.split('.', 1)

    tbl = None
    schema_name = None
    sibling_tables: list[dict] = []
    for kind in ("sources",):
        cat_dir = paths[kind]
        catalog = _load_catalog_yaml(cat_dir, dataset)
        for schema in catalog.get("schemas", []):
            schema_name_candidate = schema.get("name") or schema.get("schema_name")
            for t in schema.get("tables", []):
                if schema_part:
                    if (schema_name_candidate == schema_part) and (t.get("table_name") == table_part):
                        tbl = t
                        schema_name = schema_name_candidate
                        sibling_tables = schema.get("tables", [])
                        break
                else:
                    if t.get("table_name") == table:
                        tbl = t
                        schema_name = schema_name_candidate
                        sibling_tables = schema.get("tables", [])
                        break
            if tbl:
                break
    if tbl is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{dataset}'")

    # resolve connection config for dataset (sources only)
    conn_name = None
    for src in project.get("sources", []):
        if src["name"] == dataset:
            conn_name = src.get("connection", dataset)
            break
    if not conn_name:
        raise HTTPException(status_code=404, detail=f"No connection for dataset '{dataset}'")

    conn_cfg = None
    for c in connections.get("connections", []):
        if c.get("name") == conn_name:
            conn_cfg = c
            break
    if not conn_cfg:
        raise HTTPException(status_code=404, detail=f"Connection '{conn_name}' not found")

    # Build a minimal schema structure and run enrich_schemas to compute profile
    schema_payload = {"name": schema_name or tbl.get("schema_name") or tbl.get("schema", "public"), "tables": [tbl]}
    connector = None
    try:
        connector = profiler.load_connector(conn_cfg) if hasattr(profiler, 'load_connector') else None
    except Exception:
        connector = None

    # fallback: use core.connectors factory
    if connector is None:
        from core.connectors import load_connector as _lc
        connector = _lc(conn_cfg)

    try:
        connector.connect()
        profiled = profiler.enrich_schemas(connector, [schema_payload])
        # return the first table found
        if profiled and profiled[0].get("tables"):
            fresh_tbl = profiled[0]["tables"][0]
            # Re-run name/type FK inference using sibling tables' *stored* catalog
            # stats (no live re-query needed for them) so a single-table refresh
            # still has full cross-table context, not just this one table.
            combined = [
                fresh_tbl if t.get("table_name") == tbl.get("table_name") else t
                for t in sibling_tables
            ] or [fresh_tbl]
            profiler._infer_relations_for_schema(combined)
            return fresh_tbl
        return tbl
    finally:
        connector.close()


@router.get("/{dataset}/{table}/profile")
async def table_profile(
    dataset: str,
    table: str,
    paths: dict = Depends(get_paths),
    connections: dict = Depends(get_connections),
    project: dict = Depends(get_project),
):
    """Run an on-demand profile for a specific table using the connector.

    This does not modify stored catalogs; it computes enhanced profiling
    metrics on-demand and returns a table-shaped dict similar to the
    catalog table entry but with extra profiling fields.
    """
    return _compute_table_profile(dataset, table, paths, connections, project)


# ---------------------------------------------------------------------------
# Profile refresh — computes live profile AND writes stats back to the YAML
# so they survive page reloads and server restarts.
# Only profiling stats are overwritten; descriptions, governance metadata,
# and annotation overlays are preserved exactly.
# ---------------------------------------------------------------------------


def _rescore_table_dq(dq_service, dataset: str, schema_name: str, table_name: str, profile: dict) -> None:
    """Re-score every column's DQ + roll up the dataset badge after a profile refresh.

    Run via run_in_executor — semantic resolution + validators can take many seconds for a
    column-heavy table, and must never block the event loop (and therefore every other
    concurrent request) for that whole duration.
    """
    for col in profile.get("columns", []) or []:
        col_name = col.get("name")
        if not col_name:
            continue
        try:
            dq_service.score_and_persist(dataset, schema_name, table_name, col_name)
        except Exception:
            logger.exception(
                "DQ re-score failed after profile refresh dataset=%r table=%r "
                "column=%r", dataset, table_name, col_name,
            )
    try:
        dq_service.score_and_persist_dataset(dataset, schema_name, table_name)
    except Exception:
        logger.exception(
            "DQ dataset re-roll failed after profile refresh dataset=%r table=%r",
            dataset, table_name,
        )


def _resolve_table_semantic(
    resolver: SemanticResolver, dataset: str, schema_name: str | None, table_name: str, profile: dict,
) -> dict | None:
    """Re-derive semantic types for every column from the freshly-refreshed profile.

    SD-R5 (2026-08-12): a profile refresh now always re-derives semantic types too,
    the same forced pairing this module already gives DQ — so semantic types can
    never silently lag a fresh profile either. Non-confirmed fields are re-derived
    (no LLM); confirmed/rejected steward decisions are untouched (resolver sticky
    rule). Run via run_in_executor for the same reason as ``_rescore_table_dq``.
    Returns the resolver's ``{entity, columns, findings}`` result, or ``None`` on
    failure (logged, never raised — must not turn a successful profile refresh
    into a reported table error).
    """
    try:
        return resolver.resolve_table(
            source=dataset, schema=schema_name, table=profile, include_ai=False, persist=True,
        )
    except Exception:
        logger.exception(
            "Semantic-type resolve failed after profile refresh dataset=%r table=%r",
            dataset, table_name,
        )
        return None


@router.post("/{dataset}/{table}/refresh")
async def refresh_table_profile(
    dataset: str,
    table: str,
    paths: dict = Depends(get_paths),
    connections: dict = Depends(get_connections),
    project: dict = Depends(get_project),
    dq_service=Depends(get_dq_service),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Compute a live profile for a table and persist the stats back to the
    source YAML catalog.

    Profiling stats (null percentages, distinct counts, inferred primary keys,
    etc.) are overwritten. All other fields — descriptions, governance state,
    annotation overlays — are left untouched.

    A profile refresh can change the signals every column's semantic type and
    DQ score were computed from, so it always re-derives both for every column
    too (SD-R5, 2026-08-12) — exception-isolated per column/table so a
    semantic/DQ failure never breaks the profile refresh response. This is a
    single-table action; the forced pairing keeps "Last evaluated" in lockstep
    with "Last profiled at" without a separate opt-in step.
    """
    loop = asyncio.get_event_loop()
    profile = await loop.run_in_executor(
        None, partial(_compute_table_profile, dataset, table, paths, connections, project)
    )

    schema_name = profile.get("schema_name")
    table_name = profile.get("table_name") or table

    # Write stats back to the source catalog so they persist across restarts
    # (respects catalog_backend — yaml patches the file in place; postgres updates
    # only this table's row, so it doesn't require the YAML file to exist).
    catalog_path = paths["sources"] / f"{dataset}.yaml"
    from core.catalog_db import backend as _catalog_backend
    if catalog_path.exists() or _catalog_backend() == "postgres":
        await loop.run_in_executor(
            None, write_table_profile_dispatch, catalog_path, schema_name, table_name, profile
        )

    # Semantic resolve BEFORE DQ rescore — DQ's signal snapshot reads whatever
    # semantic record currently exists, so it must see the freshly-resolved one.
    resolver = SemanticResolver(store=semantic_store, config=ResolverConfig.from_project(project))
    sem_result = await loop.run_in_executor(
        None, _resolve_table_semantic, resolver, dataset, schema_name, table_name, profile
    )
    if sem_result is not None:
        audit_store.log_business(
            event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
            subject_type="table",
            subject_id=f"{dataset}:{schema_name or ''}.{table_name}",
            payload={
                "source": dataset, "schema": schema_name, "table": table_name,
                "include_ai": False, "column_count": len(sem_result["columns"]),
                "finding_count": len(sem_result["findings"]),
            },
        )
        emit_governance_event(
            audit_events.SEMANTIC_TYPES_RESOLVED,
            {
                "source": dataset, "schema": schema_name, "table": table_name,
                "column_count": len(sem_result["columns"]), "finding_count": len(sem_result["findings"]),
            },
        )

    if dq_service is not None:
        # Off the event loop — DQ re-scoring (semantic resolution + validators, per column)
        # can take many seconds for a column-heavy table and must never block other requests.
        await loop.run_in_executor(
            None, _rescore_table_dq, dq_service, dataset, schema_name, table_name, profile
        )

    return profile


# ---------------------------------------------------------------------------
# Source-level bulk profile rebuild — streams progress as SSE
# ---------------------------------------------------------------------------

@router.post("/{dataset}/rebuild-all")
async def rebuild_source_profiles(
    dataset: str,
    paths: dict = Depends(get_paths),
    connections: dict = Depends(get_connections),
    project: dict = Depends(get_project),
    dq_service=Depends(get_dq_service),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
    include_semantic: bool = Query(default=True),
    include_dq: bool = Query(default=True),
):
    """Re-profile every table in a source dataset from the live database.

    Streams Server-Sent Events so the UI can show a real-time progress tracker.
    Each table's stats are written back to the source YAML immediately after
    profiling — descriptions, governance metadata, and annotations are preserved.

    SD-R5 (2026-08-12): unlike a single-table refresh (which always re-derives
    semantic types + DQ too, unconditionally — see ``refresh_table_profile``),
    a bulk rebuild can span many tables, so ``include_semantic``/``include_dq``
    (default ``True``, opt-out) let the caller skip the heavier steps when only
    fresh catalog stats are wanted. Whichever steps run, they run for every
    table via the SAME per-table helpers the single-table endpoint uses — this
    is genuinely "N × single-table refresh", not a separate implementation.

    SSE event types:
        started   — job kicked off, includes total table count + which steps will run
        progress  — one table done, includes index, table name, elapsed, estimated_remaining
        error     — one table failed (non-fatal, continues to next)
        done      — all tables processed
    """
    # Resolve all tables from the catalog (respects catalog_backend — no on-disk
    # file to gate on in postgres mode, so 404 is decided from the dispatched result).
    catalog_path = paths["sources"] / f"{dataset}.yaml"
    catalog = load_catalog_dispatch(catalog_path)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"Source catalog '{dataset}' not found")

    # Collect all (schema_name, table_name, table_dict) triples
    all_tables: list[tuple[str, str, dict]] = []
    for schema in catalog.get("schemas", []):
        schema_name = schema.get("name", "")
        for tbl in schema.get("tables", []):
            tname = tbl.get("table_name") or tbl.get("name", "")
            all_tables.append((schema_name, tname, tbl))

    total = len(all_tables)
    resolver = (
        SemanticResolver(store=semantic_store, config=ResolverConfig.from_project(project))
        if include_semantic else None
    )

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {_json.dumps(data, default=str)}\n\n"

    async def generate():
        yield _sse("started", {
            "total": total, "dataset": dataset,
            "include_semantic": include_semantic, "include_dq": include_dq,
        })

        loop = asyncio.get_event_loop()
        start_ts = time.monotonic()
        completed = 0
        failed = 0
        sem_table_count = 0
        sem_column_count = 0

        # One coalesced write per store for the WHOLE source pass instead of one
        # per table — both batch() context managers are nestable no-ops when the
        # respective step is skipped or backend is Postgres (see SemanticTypeStore/
        # DQScoreStore's own batch() docstrings).
        with (semantic_store.batch() if include_semantic else nullcontext()), \
             (dq_service.batch() if include_dq and dq_service is not None else nullcontext()):
            for idx, (schema_name, tname, tbl) in enumerate(all_tables):
                table_param = f"{schema_name}.{tname}" if schema_name else tname
                try:
                    profile = await loop.run_in_executor(
                        None,
                        partial(_compute_table_profile, dataset, table_param, paths, connections, project),
                    )
                    await loop.run_in_executor(
                        None, write_table_profile_dispatch, catalog_path, schema_name, tname, profile
                    )
                    if resolver is not None:
                        sem_result = await loop.run_in_executor(
                            None, _resolve_table_semantic, resolver, dataset, schema_name, tname, profile
                        )
                        if sem_result is not None:
                            sem_table_count += 1
                            sem_column_count += len(sem_result["columns"])
                    if include_dq and dq_service is not None:
                        await loop.run_in_executor(
                            None, _rescore_table_dq, dq_service, dataset, schema_name, tname, profile
                        )
                    completed += 1
                    status = "ok"
                    error_msg = None
                except Exception as exc:
                    failed += 1
                    status = "error"
                    error_msg = str(exc)

                elapsed = time.monotonic() - start_ts
                done_so_far = idx + 1
                avg_per_table = elapsed / done_so_far
                remaining_tables = total - done_so_far
                estimated_remaining = avg_per_table * remaining_tables if remaining_tables > 0 else 0

                yield _sse("progress", {
                    "index": done_so_far,
                    "total": total,
                    "table": tname,
                    "schema": schema_name,
                    "status": status,
                    "error": error_msg,
                    "elapsed": round(elapsed, 1),
                    "estimated_remaining": round(estimated_remaining, 1),
                    "completed": completed,
                    "failed": failed,
                })

        if resolver is not None and sem_table_count:
            audit_store.log_business(
                event_type=audit_events.SEMANTIC_TYPES_RESOLVED,
                subject_type="source",
                subject_id=dataset,
                payload={
                    "source": dataset, "scope": "source",
                    "table_count": sem_table_count, "column_count": sem_column_count,
                },
            )
            emit_governance_event(
                audit_events.SEMANTIC_TYPES_RESOLVED,
                {
                    "source": dataset, "scope": "source",
                    "table_count": sem_table_count, "column_count": sem_column_count,
                },
            )

        total_elapsed = time.monotonic() - start_ts
        yield _sse("done", {
            "total": total,
            "completed": completed,
            "failed": failed,
            "elapsed": round(total_elapsed, 1),
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Profile reset (add-profile-reset) — returns a dataset/table, or an entire
# source, to the same pre-profiling shape a freshly onboarded (never profiled)
# table already has. Streams progress over SSE (D6), reusing the started/
# progress/error/done shape above — but unlike a profile refresh/rebuild,
# nothing commits until the WHOLE call finishes (one shared transaction, D3):
# the stream is purely observational, and on failure it reports that
# everything was rolled back rather than a partial success.
# ---------------------------------------------------------------------------

class ProfileResetRequest(BaseModel):
    actor: str | None = None


def _reset_sse_response(work: Callable[[Callable[[str, dict], None]], dict]):
    """Shared SSE plumbing for both reset endpoints: runs *work* (a blocking call into
    core.profile_reset) in a worker thread, bridging its synchronous ``on_progress``
    callback into this async generator via a thread-safe queue so progress streams in
    near real time even though the whole reset is one uncommitted transaction until it
    returns.
    """
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {_json.dumps(data, default=str)}\n\n"

    async def generate():
        yield _sse("started", {})

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()

        def _on_progress(step: str, detail: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("progress", {"step": step, **detail}))

        def _run() -> None:
            try:
                result = work(_on_progress)
                loop.call_soon_threadsafe(queue.put_nowait, ("done", result))
            except Exception as exc:  # noqa: BLE001 — reported over SSE, not raised
                logger.exception("Profile reset failed")
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, (_DONE, None))

        executor_future = loop.run_in_executor(None, _run)
        while True:
            kind, payload = await queue.get()
            if kind is _DONE:
                break
            if kind == "progress":
                yield _sse("progress", payload)
            elif kind == "done":
                yield _sse("done", {"result": payload})
            elif kind == "error":
                yield _sse("error", {"message": payload, "rolled_back": True})
        await executor_future

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{dataset}/{table}/reset")
async def reset_table_profile(dataset: str, table: str, body: ProfileResetRequest = ProfileResetRequest()):
    """Reset one dataset/table back to a pre-profiling baseline.

    Clears catalog stats, semantic types, DQ scores, Interpretation lifecycle + content,
    Reference Data, reference-set binding + its review, and annotations — see
    openspec/changes/add-profile-reset/design.md. Postgres-only (no YAML-mode support, by
    design). Idempotent: resetting an already-blank table is a no-op success.
    """
    from core.profile_reset import reset_table

    schema_part = None
    table_part = table
    if "." in table:
        schema_part, table_part = table.split(".", 1)

    return _reset_sse_response(
        lambda on_progress: reset_table(
            dataset, schema_part, table_part, actor=body.actor, on_progress=on_progress,
        )
    )


@router.post("/{dataset}/reset")
async def reset_source_profiles(dataset: str, body: ProfileResetRequest = ProfileResetRequest()):
    """Reset every table in a source back to a pre-profiling baseline.

    ONE transaction spans every table in the source (D3, user decision) — a single failing
    table rolls back every table's work for this call, not just its own. See
    openspec/changes/add-profile-reset/design.md.
    """
    from core.profile_reset import reset_source

    return _reset_sse_response(
        lambda on_progress: reset_source(dataset, actor=body.actor, on_progress=on_progress)
    )


@router.get("/{dataset}/{table}/assessment")
async def table_assessment(
    dataset: str,
    table: str,
    include_ai: bool = False,
    refresh: bool = False,
    paths: dict = Depends(get_paths),
    connections: dict = Depends(get_connections),
    project: dict = Depends(get_project),
):
    """Run the Smart Data Assessment for a table.

    Computes the on-demand profile and derives advisory findings from it. These
    findings are observations only — they never block data onboarding.

    Query params:
        include_ai: also generate AI-suggested findings (cached by data shape).
        refresh:    bypass the AI cache and regenerate.
    """
    from core import assessment

    profile = _compute_table_profile(dataset, table, paths, connections, project)
    return assessment.assess_table(profile, include_ai=include_ai, refresh_ai=refresh)


def _build_discovery_prompt(table: dict, connection_name: str | None) -> str:
    """Build a system prompt scoped to the selected table."""
    col_lines = []
    for c in table.get("columns", []):
        parts = [f"  - {c.get('name', '?')} ({c.get('data_type', '?')})"]
        if c.get("description"):
            parts.append(f"    desc: {c['description']}")
        if c.get("distinct_count") is not None:
            parts.append(f"    distinct: {c['distinct_count']}")
        if c.get("null_pct") is not None:
            parts.append(f"    null%: {c['null_pct']:.1%}")
        if c.get("sample_values"):
            samples = c["sample_values"]
            if isinstance(samples, list):
                samples = ", ".join(str(s) for s in samples[:2])
            parts.append(f"    samples: {samples}")
        col_lines.append("\n".join(parts))

    cols_text = "\n".join(col_lines) if col_lines else "  (no columns)"
    conn_note = ""
    if connection_name:
        schema = table.get("schema_name", table.get("schema", ""))
        tname = table.get("table_name", table.get("table", ""))
        conn_note = (
            f"\n\nDatabase connection: {connection_name}\n"
            f'You can use the query_data tool with connection_name="{connection_name}" to run SQL queries.\n'
            f'Tables are in the "{schema}" schema. '
            f"Use schema-qualified names (e.g. {schema}.{tname})."
        )

    schema = table.get("schema_name", table.get("schema", ""))
    tname = table.get("table_name", table.get("table", ""))
    pk = table.get("primary_key", [])
    return (
        f"You are a data exploration assistant. The user is inspecting a specific database table.\n\n"
        f"Table: {schema}.{tname}\n"
        f"Description: {table.get('description') or 'N/A'}\n"
        f"Row count: {table.get('row_count') or 'N/A'}\n"
        f"Primary key: {', '.join(pk) if pk else 'None'}\n\n"
        f"Columns:\n{cols_text}\n"
        f"{conn_note}\n\n"
        f"Answer questions about this table's structure, data quality, and contents. "
        f"When the user asks to see data or create visualizations, use the query_data and render_chart tools. "
        f"Be concise and helpful."
    )


def _query_duckdb_for_chart(sql: str, connection_name: str | None) -> list[dict] | str:
    """Execute read-only SQL for chart data. Returns rows or error string."""
    if not connection_name:
        return "No database connection available."
    from agents.chat_agent import _resolve_duckdb_path, _MAX_QUERY_ROWS
    import duckdb

    resolved = _resolve_duckdb_path(connection_name)
    if isinstance(resolved, str):
        return resolved
    try:
        conn = duckdb.connect(str(resolved), read_only=True)
        try:
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchmany(_MAX_QUERY_ROWS)
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
    except Exception as exc:
        return f"SQL error: {exc}"


def _visuals_from_tool_results(
    tool_results: list[dict], connection_name: str | None
) -> list[dict]:
    """Extract renderable visuals (charts, data tables) from tool results."""
    visuals: list[dict] = []
    for tr in tool_results:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if not isinstance(result, dict):
            continue

        if tool_name == "query_data" and "data" in result:
            visuals.append({"type": "dataframe", "data": result["data"], "columns": result.get("columns", [])})

        elif tool_name == "render_chart" and "chart_spec" in result:
            spec = result["chart_spec"]
            data_sql = spec.get("data_sql")
            conn = spec.get("connection_name", connection_name)
            if data_sql and conn:
                rows = _query_duckdb_for_chart(data_sql, conn)
                if isinstance(rows, list) and rows:
                    visuals.append({"type": "chart", "spec": spec, "data": rows})
                elif isinstance(rows, str):
                    visuals.append({"type": "error", "message": rows})
    return visuals


class DiscoveryChatRequest(BaseModel):
    messages: list[dict]


@router.post("/{dataset}/{table}/chat")
async def discovery_chat(
    dataset: str,
    table: str,
    body: DiscoveryChatRequest,
    paths: dict = Depends(get_paths),
    project: dict = Depends(get_project),
    agent_cfg: dict = Depends(get_agent_config),
):
    """Chat scoped to a specific table with context-aware system prompt."""
    # Load table metadata
    tbl = None
    # Load table metadata
    schema_part = None
    table_part = table
    if "." in table:
        schema_part, table_part = table.split('.', 1)

    tbl = None
    for kind in ("sources",):
        cat_dir = paths[kind]
        catalog = _load_catalog_yaml(cat_dir, dataset)
        for schema in catalog.get("schemas", []):
            schema_name_candidate = schema.get("name") or schema.get("schema_name")
            for t in schema.get("tables", []):
                if schema_part:
                    if (schema_name_candidate == schema_part) and (t.get("table_name") == table_part):
                        tbl = t
                        break
                else:
                    if t.get("table_name") == table:
                        tbl = t
                        break
            if tbl:
                break
    if tbl is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{dataset}'")

    # Resolve connection name for the dataset (sources only)
    conn_name = None
    for src in project.get("sources", []):
        if src["name"] == dataset:
            conn_name = src.get("connection", dataset)
            break

    system_prompt = _build_discovery_prompt(tbl, conn_name)

    from agents.chat_agent import chat

    loop = asyncio.get_running_loop()
    reply_text, tool_results = await loop.run_in_executor(
        None,
        partial(chat, body.messages, agent_cfg, system_prompt),
    )

    # Process tool results for charts and data tables
    visuals = _visuals_from_tool_results(tool_results, conn_name)
    return {"reply": reply_text, "visuals": visuals}
