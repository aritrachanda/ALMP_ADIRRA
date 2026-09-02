"""Shared helper for turning a blocking, callback-instrumented function into a
real-time Server-Sent Events stream.

Existing bulk endpoints (e.g. discovery.py's rebuild_source_profiles) stream
progress by looping and yielding directly, because each unit of work already
happens on the event loop between yields. This helper is for the opposite
case: a single function that does one synchronous chunk of work per stage and
needs to report progress from inside a background thread (so the event loop
isn't blocked for the whole call) — e.g. a per-column resolve loop.

No event is ever fabricated: each yielded tuple corresponds to a real `emit()`
call the worker made, in the order it made them.
"""
from __future__ import annotations

import asyncio
import json
import queue
from typing import Any, AsyncGenerator, Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")

EmitFn = Callable[[str, dict], None]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream_with_progress(
    loop: asyncio.AbstractEventLoop,
    work_fn: Callable[[EmitFn], T],
) -> AsyncGenerator[tuple[str, Any], None]:
    """Run ``work_fn(emit)`` in a background thread.

    Yields ``(event, data)`` tuples in real time as the worker calls
    ``emit(event, data)``, then a final ``("done", result)`` tuple once
    ``work_fn`` returns ``result`` — or an ``("error", {...})`` tuple if
    ``work_fn`` raises, so the stream always ends cleanly instead of leaving
    the connection hanging (the SSE response has already sent its 200 status
    by the time an error surfaces, so it cannot become a normal HTTP error
    response — it must be reported as a final event instead).
    """
    q: "queue.Queue[tuple[str, dict]]" = queue.Queue()

    def emit(event: str, data: dict) -> None:
        q.put((event, data))

    future = loop.run_in_executor(None, lambda: work_fn(emit))
    while not future.done():
        try:
            yield q.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.03)
    while True:
        try:
            yield q.get_nowait()
        except queue.Empty:
            break
    try:
        result = future.result()
    except HTTPException as exc:
        yield ("error", {"status": exc.status_code, "detail": exc.detail})
        return
    except Exception as exc:  # noqa: BLE001 - report any worker failure, never hang
        yield ("error", {"status": 500, "detail": str(exc)})
        return
    yield ("done", result)
