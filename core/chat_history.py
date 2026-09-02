"""
Chat history service — load/save chat conversations as JSON files.

Streamlit-free on purpose so the same module can back a future Django UI.

Each conversation is stored as `chat_history/<id>.json` with the shape:

    {
      "id": "2026-05-12T08-14-22_a1b2c3",
      "title": "Mapping banking to BIRD",
      "created_at": "2026-05-12T08:14:22Z",
      "updated_at": "2026-05-12T08:16:01Z",
      "messages": [
        {"role": "user", "content": "...", "ts": "..."},
        {"role": "assistant", "content": "...", "ts": "..."}
      ]
    }
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Repo-root-relative directory for chat history.
_ROOT = Path(__file__).resolve().parent.parent
CHAT_HISTORY_DIR = _ROOT / "chat_history"

_TITLE_MAX = 40
_VALID_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


@dataclass
class ConversationSummary:
    id: str
    title: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def new_conversation(first_message: Optional[str] = None) -> dict:
    """Create and persist a new (empty) conversation. Returns the conversation dict."""
    now = _now_iso()
    cid = _make_id(now)
    convo = {
        "id": cid,
        "title": _derive_title(first_message) if first_message else "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _write(convo)
    return convo


def list_conversations() -> list[ConversationSummary]:
    """Return summaries sorted by updated_at desc."""
    if not CHAT_HISTORY_DIR.exists():
        return []
    out: list[ConversationSummary] = []
    for p in CHAT_HISTORY_DIR.glob("*.json"):
        try:
            with p.open(encoding="utf-8") as fh:
                d = json.load(fh)
            out.append(
                ConversationSummary(
                    id=d.get("id", p.stem),
                    title=d.get("title", "Untitled"),
                    created_at=d.get("created_at", ""),
                    updated_at=d.get("updated_at", ""),
                )
            )
        except (OSError, json.JSONDecodeError):
            # Skip unreadable files instead of crashing the UI.
            continue
    out.sort(key=lambda c: c.updated_at, reverse=True)
    return out


def load_conversation(conversation_id: str) -> Optional[dict]:
    p = _path_for(conversation_id)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def append_message(conversation_id: str, role: str, content: str) -> dict:
    """Append a message and rewrite the file. Returns the updated conversation."""
    convo = load_conversation(conversation_id)
    if convo is None:
        raise FileNotFoundError(f"Conversation {conversation_id!r} not found.")
    now = _now_iso()
    convo["messages"].append({"role": role, "content": content, "ts": now})
    convo["updated_at"] = now
    # Auto-title from the first user message if still on the default.
    if convo.get("title") in (None, "", "New chat") and role == "user":
        convo["title"] = _derive_title(content)
    _write(convo)
    return convo


def delete_conversation(conversation_id: str) -> bool:
    p = _path_for(conversation_id)
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _path_for(conversation_id: str) -> Path:
    if not _VALID_ID.match(conversation_id):
        # Defensive: prevent path traversal via crafted IDs.
        raise ValueError(f"Invalid conversation id: {conversation_id!r}")
    return CHAT_HISTORY_DIR / f"{conversation_id}.json"


def _write(convo: dict) -> None:
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    p = _path_for(convo["id"])
    with p.open("w", encoding="utf-8") as fh:
        json.dump(convo, fh, indent=2, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_id(now_iso: str) -> str:
    stamp = now_iso.replace(":", "-").replace("Z", "")
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


def _derive_title(text: str) -> str:
    text = (text or "").strip().splitlines()[0] if text else "New chat"
    text = text[:_TITLE_MAX].rstrip()
    return text or "New chat"
