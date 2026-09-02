"""Minimal in-process governance event registry.

U0 scope: registry + emission points only. No subscribers yet — DQ subscribes
in U2. Handlers are exception-isolated so a failing handler never breaks the
emitter (logged and skipped, emission continues to remaining handlers).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)


def register(event_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
    """Register *handler* to be called whenever *event_type* is emitted."""
    _HANDLERS[event_type].append(handler)


def register_once(event_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
    """Register *handler* only if that exact handler is not already registered.

    Idempotent across repeated calls (e.g. one per app lifespan in tests) — the
    same handler object is never registered twice for the same event type.
    """
    if handler not in _HANDLERS.get(event_type, ()):
        _HANDLERS[event_type].append(handler)


def emit(event_type: str, payload: dict[str, Any]) -> None:
    """Call every handler registered for *event_type* with *payload*.

    A handler raising an exception is logged and skipped — it never
    prevents other handlers from running or propagates to the caller.
    """
    for handler in list(_HANDLERS.get(event_type, ())):
        try:
            handler(payload)
        except Exception:
            logger.exception("Governance event handler failed for event_type=%r", event_type)


def clear() -> None:
    """Remove all registered handlers. Intended for test isolation."""
    _HANDLERS.clear()
