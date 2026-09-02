"""Unit tests for api.sse_utils.stream_with_progress.

Root cause of a real hang (2026-08-17): a worker function raising ANY exception
(e.g. a stale localStorage selection reaching the backend with table='*') used
to propagate straight out of the async generator, after the SSE response's 200
status had already been sent — the connection was left dangling with no final
event, and the frontend spun forever waiting for one. Fixed so the stream
always ends with a clean event: "done" on success, "error" on failure.
"""
from __future__ import annotations

import asyncio

from fastapi import HTTPException

from api.sse_utils import stream_with_progress


def _run(work_fn):
    async def _collect():
        loop = asyncio.get_running_loop()
        events = []
        async for event, data in stream_with_progress(loop, work_fn):
            events.append((event, data))
        return events

    return asyncio.run(_collect())


def test_normal_completion_yields_progress_then_done():
    def work(emit):
        emit("progress", {"completed": 1})
        emit("detail", {"text": "working"})
        return {"ok": True}

    events = _run(work)
    assert ("progress", {"completed": 1}) in events
    assert ("detail", {"text": "working"}) in events
    assert events[-1] == ("done", {"ok": True})


def test_http_exception_yields_error_event_instead_of_raising():
    def work(emit):
        raise HTTPException(status_code=404, detail="Table '*' not found in 'ALM Bank'")

    events = _run(work)
    assert events == [("error", {"status": 404, "detail": "Table '*' not found in 'ALM Bank'"})]


def test_generic_exception_yields_error_event_with_500():
    def work(emit):
        raise ValueError("boom")

    events = _run(work)
    assert events == [("error", {"status": 500, "detail": "boom"})]
