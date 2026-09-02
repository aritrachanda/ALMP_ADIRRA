"""Generic JSON-serialization helpers with no feature ownership — safe for any caller."""
from __future__ import annotations

from datetime import date, datetime


def json_default(obj):
    """Fallback for values the standard JSON encoder can't handle (date/datetime/Decimal/etc).

    date/datetime use ISO 8601 (``.isoformat()``); everything else falls back to ``str()``.
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)
