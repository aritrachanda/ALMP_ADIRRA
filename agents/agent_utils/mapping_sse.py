"""
mapping_sse.py — Format MappingEvent dicts as Server-Sent Events text frames.

Used by the future FastAPI backend to stream mapping progress to the Quasar
frontend. See openspec/changes/add-fastapi-backend/design.md § D3.

SSE event mapping:
    MappingEvent.type  →  SSE event name
    ──────────────────────────────────────
    analyzing          →  status
    candidates         →  status
    scoring            →  status
    columns            →  candidate
    validating         →  status
    table_done         →  candidate
    error              →  error
    done               →  done
"""
from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from agents.agent_utils.mapping_events import MappingEvent

# Internal event type → SSE event name
_SSE_EVENT_MAP: dict[str, str] = {
    "analyzing": "status",
    "candidates": "status",
    "scoring": "status",
    "columns": "candidate",
    "validating": "status",
    "table_done": "candidate",
    "error": "error",
    "done": "done",
}


def _serialize_event(event: MappingEvent) -> dict[str, Any]:
    """Build the JSON payload for an SSE data line.

    Strips the large 'mapping' dict from 'done' events to keep the frame
    lightweight — the client should fetch the final mapping via GET.
    """
    payload: dict[str, Any] = {
        "type": event.get("type"),
        "target_table": event.get("target_table"),
        "index": event.get("index", 0),
        "total": event.get("total", 0),
        "message": event.get("message", ""),
        "timestamp": event.get("timestamp", ""),
    }
    data = event.get("data")
    if data and event.get("type") != "done":
        payload["data"] = data
    elif event.get("type") == "done" and data:
        # Include summary but not the full mapping blob
        payload["data"] = {
            k: v for k, v in data.items() if k != "mapping"
        }
    return payload


def format_sse_events(
    events: Generator[MappingEvent, None, Any],
) -> Generator[str, None, None]:
    """Consume a MappingEvent generator and yield SSE text frames.

    Each yielded string is a complete SSE message:
        event: <name>\\n
        data: <json>\\n
        \\n
    """
    try:
        while True:
            event = next(events)
            sse_name = _SSE_EVENT_MAP.get(event.get("type", ""), "status")
            payload = _serialize_event(event)
            data_line = json.dumps(payload, default=str)
            yield f"event: {sse_name}\ndata: {data_line}\n\n"
    except StopIteration:
        pass
