"""Chat API routes."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_agent_config
from api.llm_errors import scrub_secrets as _scrub_secrets
from api.schemas.chat import SendMessageRequest

router = APIRouter(prefix="/chat", tags=["chat"])

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _format_chat_error(exc: Exception, api_key_env: str) -> dict:
    """Turn a backend/LLM failure into a provider-agnostic, user-facing error payload."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    name = type(exc).__name__
    if status in (401, 403):
        summary = ("I couldn't reach the AI service — access was denied. This usually means the "
                   "API key is wrong or the AI resource's network/firewall rules block this machine.")
    elif status == 404:
        summary = "I couldn't reach the AI service — the configured model deployment wasn't found."
    elif status == 429:
        summary = "The AI service is busy right now (rate limit). Please try again in a moment."
    elif isinstance(status, int) and status >= 500:
        summary = "The AI service reported an internal error. Please try again shortly."
    elif "Connection" in name or "Timeout" in name:
        summary = "I couldn't reach the AI service — the connection failed or timed out."
    elif isinstance(exc, ValueError):
        summary = "The AI service isn't configured. Set the API key and endpoint in the .env file."
    else:
        summary = "Something went wrong while contacting the AI service."
    return {"summary": summary, "detail": _scrub_secrets(str(exc), api_key_env), "status": status}



@router.get("/conversations")
async def list_conversations():
    from core.chat_history import list_conversations
    summaries = list_conversations()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at, "updated_at": s.updated_at} for s in summaries]


@router.post("/conversations")
async def create_conversation():
    from core.chat_history import new_conversation
    return new_conversation()


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    from core.chat_history import load_conversation
    convo = load_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")
    return convo


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    agent_cfg: dict = Depends(get_agent_config),
):
    from core.chat_history import load_conversation, append_message
    from agents.chat_agent import chat, _build_system_prompt

    convo = load_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

    append_message(conversation_id, "user", body.content)
    convo = load_conversation(conversation_id)

    system_prompt = None
    if body.context:
        system_prompt = _build_system_prompt() + "\n\n" + body.context

    try:
        reply_text, tool_calls = chat(convo["messages"], agent_cfg, system_prompt=system_prompt)
    except Exception as exc:  # noqa: BLE001 — surface any LLM/transport failure as a friendly payload
        # Ephemeral: the failed assistant turn is NOT persisted; only the user message stays.
        return {"error": _format_chat_error(exc, agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"))}

    updated = append_message(conversation_id, "assistant", reply_text)

    from api.routes.discovery import _visuals_from_tool_results
    visuals = _visuals_from_tool_results(tool_calls, None)
    return {**updated, "visuals": visuals}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    from core.chat_history import delete_conversation
    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")
    return {"status": "deleted"}
