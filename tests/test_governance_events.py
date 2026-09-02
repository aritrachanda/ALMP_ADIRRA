"""Tests for core.governance_events — minimal in-process event registry (U0 Task 4)."""
from __future__ import annotations

import pytest

from core import governance_events


@pytest.fixture(autouse=True)
def _clear_registry():
    governance_events.clear()
    yield
    governance_events.clear()


def test_register_and_emit_calls_handler():
    received = []
    governance_events.register("test.event", lambda payload: received.append(payload))

    governance_events.emit("test.event", {"foo": "bar"})

    assert received == [{"foo": "bar"}]


def test_emit_calls_multiple_handlers_in_registration_order():
    calls = []
    governance_events.register("test.event", lambda payload: calls.append("first"))
    governance_events.register("test.event", lambda payload: calls.append("second"))

    governance_events.emit("test.event", {})

    assert calls == ["first", "second"]


def test_emit_with_no_handlers_does_nothing():
    # Should not raise even though nothing is registered for this event type.
    governance_events.emit("unregistered.event", {"foo": "bar"})


def test_failing_handler_is_isolated_and_does_not_break_other_handlers():
    calls = []

    def bad_handler(payload):
        raise RuntimeError("boom")

    def good_handler(payload):
        calls.append(payload)

    governance_events.register("test.event", bad_handler)
    governance_events.register("test.event", good_handler)

    # Must not raise despite the first handler failing.
    governance_events.emit("test.event", {"ok": True})

    assert calls == [{"ok": True}]


def test_emit_does_not_leak_across_event_types():
    received = []
    governance_events.register("event.a", lambda payload: received.append(payload))

    governance_events.emit("event.b", {"should": "not-arrive"})

    assert received == []
