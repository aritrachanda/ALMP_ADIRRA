"""Mapping API routes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import get_paths, get_agent_config, get_project, get_audit_store
from api.llm_errors import format_llm_error
from api.schemas.mapping import MappingRunRequest, CandidateUpdateBatch
from core.audit import AuditStore
from core.audit import events as audit_events

router = APIRouter(prefix="/mappings", tags=["mappings"])

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _list_mapping_files(mappings_dir: Path) -> list[dict]:
    items = []
    for p in sorted(mappings_dir.glob("*.yaml")):
        m = re.match(r"^(.+?)_to_(.+)$", p.stem)
        if m:
            items.append({"source": m.group(1), "target": m.group(2), "filename": p.name})
    return items


def _mapping_path(mappings_dir: Path, source: str, target: str) -> Path:
    return mappings_dir / f"{source}_to_{target}.yaml"


def _load_mapping(mappings_dir: Path, source: str, target: str) -> dict:
    path = _mapping_path(mappings_dir, source, target)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Mapping '{source}_to_{target}' not found")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _save_mapping_yaml(mappings_dir: Path, source: str, target: str, data: dict) -> None:
    path = _mapping_path(mappings_dir, source, target)
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)


@router.get("")
async def list_mappings(paths: dict = Depends(get_paths)):
    return _list_mapping_files(paths["mappings"])


@router.get("/{source}/{target}")
async def get_mapping(source: str, target: str, paths: dict = Depends(get_paths)):
    return _load_mapping(paths["mappings"], source, target)


@router.post("/{source}/{target}/run")
async def run_mapping(
    source: str,
    target: str,
    body: MappingRunRequest,
    paths: dict = Depends(get_paths),
    agent_cfg: dict = Depends(get_agent_config),
    project: dict = Depends(get_project),
):
    from agents.mapping_agent import load_catalog, map_source_to_target, save_mapping
    from core.annotations import load_annotations

    source_catalog = load_catalog(source, paths["sources"], kind="source")
    target_catalog = load_catalog(target, paths["targets"], kind="target")
    source_annotations = load_annotations(source, paths["sources"])
    target_annotations = load_annotations(target, paths["targets"])
    target_tables = set(body.selected_tables) if body.selected_tables else None

    mapping = map_source_to_target(
        source_catalog,
        target_catalog,
        agent_cfg,
        dataset_context=body.dataset_context,
        target_tables=target_tables,
        source_annotations=source_annotations,
        target_annotations=target_annotations,
    )
    save_mapping(source, target, mapping, paths["mappings"])
    return mapping


@router.post("/{source}/{target}/run-stream")
async def run_mapping_stream(
    source: str,
    target: str,
    body: MappingRunRequest,
    paths: dict = Depends(get_paths),
    agent_cfg: dict = Depends(get_agent_config),
):
    import asyncio
    import json as _json
    import logging
    from agents.mapping_agent import load_catalog, map_source_to_target_stream, save_mapping
    from agents.agent_utils.mapping_sse import _SSE_EVENT_MAP, _serialize_event
    from core.annotations import load_annotations

    logger = logging.getLogger("mapping_stream")

    source_catalog = load_catalog(source, paths["sources"], kind="source")
    target_catalog = load_catalog(target, paths["targets"], kind="target")
    source_annotations = load_annotations(source, paths["sources"])
    target_annotations = load_annotations(target, paths["targets"])
    target_tables = set(body.selected_tables) if body.selected_tables else None

    events_gen = map_source_to_target_stream(
        source_catalog,
        target_catalog,
        agent_cfg,
        dataset_context=body.dataset_context,
        target_tables=target_tables,
        source_annotations=source_annotations,
        target_annotations=target_annotations,
    )

    async def generate():
        """Async generator that runs the blocking mapping generator in a thread."""
        mapping = None
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _run_sync():
            nonlocal mapping
            try:
                for event in events_gen:
                    if event.get("type") == "done":
                        mapping = (event.get("data") or {}).get("mapping")
                    sse_name = _SSE_EVENT_MAP.get(event.get("type", ""), "status")
                    payload = _serialize_event(event)
                    data_line = _json.dumps(payload, default=str)
                    frame = f"event: {sse_name}\ndata: {data_line}\n\n"
                    loop.call_soon_threadsafe(queue.put_nowait, frame)
            except Exception as exc:
                logger.exception("Mapping stream error")
                err = format_llm_error(exc, agent_cfg.get("api_key_env"))
                error_data = _json.dumps({"type": "error", "message": err["summary"], "error": err})
                frame = f"event: error\ndata: {error_data}\n\n"
                loop.call_soon_threadsafe(queue.put_nowait, frame)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        task = loop.run_in_executor(None, _run_sync)

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            logger.debug("SSE frame: %s", item[:80])
            yield item

        await task

        if mapping:
            save_mapping(source, target, mapping, paths["mappings"])

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{source}/{target}/candidates")
async def update_candidates(
    source: str,
    target: str,
    body: CandidateUpdateBatch,
    paths: dict = Depends(get_paths),
    store: AuditStore = Depends(get_audit_store),
):
    mapping = _load_mapping(paths["mappings"], source, target)
    updates_by_key = {
        (u.target_schema, u.target_table, u.target_column): u.status
        for u in body.updates
    }
    for tbl in mapping.get("tables", []):
        for col in tbl.get("columns", []):
            key = (tbl.get("target_schema"), tbl.get("target_table"), col.get("target_column"))
            if key in updates_by_key:
                new_status = updates_by_key[key]
                old_status = col.get("status")
                col["status"] = new_status
                if new_status != old_status:
                    event_type = (
                        audit_events.MAPPING_CANDIDATE_ACCEPTED
                        if new_status == "accepted"
                        else audit_events.MAPPING_CANDIDATE_REJECTED
                    )
                    subject_id = f"{source}_to_{target}:{col.get('source_column', '')}→{col.get('target_column', '')}"
                    store.log_business(
                        event_type,
                        "mapping",
                        subject_id,
                        {
                            "source": source,
                            "target": target,
                            "target_schema": tbl.get("target_schema"),
                            "target_table": tbl.get("target_table"),
                            "source_column": col.get("source_column"),
                            "target_column": col.get("target_column"),
                            "confidence": col.get("confidence"),
                            "previous_status": old_status,
                        },
                    )
    _save_mapping_yaml(paths["mappings"], source, target, mapping)
    return mapping


@router.put("/{source}/{target}")
async def save_mapping_full(
    source: str,
    target: str,
    body: dict,
    paths: dict = Depends(get_paths),
):
    _save_mapping_yaml(paths["mappings"], source, target, body)
    return {"status": "saved"}
