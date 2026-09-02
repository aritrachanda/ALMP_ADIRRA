"""
mapping_events.py — Structured event types for mapping agent streaming.

Events are yielded by the mapping agent generator and consumed by the UI
(Streamlit progress feed) or formatted as SSE frames for the FastAPI backend.

Event flow per target table:
  analyzing     → source schema analysis
  candidates    → candidate target tables found (with names)
  scoring       → table-level match scored
  columns       → per-column mapping results (individual lines)
  validating    → transformation validation pass
  table_done    → table complete with summary

Final event:
  done          → entire mapping run complete
  error         → unrecoverable error for a table
"""
from __future__ import annotations

import datetime
from typing import Any, Literal, TypedDict


EventType = Literal[
    "analyzing",
    "candidates",
    "scoring",
    "columns",
    "validating",
    "table_done",
    "error",
    "done",
]


class MappingEvent(TypedDict, total=False):
    """A single progress event emitted during a mapping run."""

    type: EventType
    target_table: str | None
    index: int          # 1-based index of the current target table
    total: int          # total number of target tables to process
    message: str        # human-readable status message
    data: dict[str, Any] | None  # optional structured payload
    timestamp: str      # ISO 8601 timestamp


def make_event(
    event_type: EventType,
    message: str,
    *,
    target_table: str | None = None,
    index: int = 0,
    total: int = 0,
    data: dict[str, Any] | None = None,
) -> MappingEvent:
    """Construct a MappingEvent with the current timestamp."""
    return MappingEvent(
        type=event_type,
        target_table=target_table,
        index=index,
        total=total,
        message=message,
        data=data,
        timestamp=datetime.datetime.now().isoformat(timespec="milliseconds"),
    )
