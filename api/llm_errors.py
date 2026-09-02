"""Shared, provider-agnostic formatting for LLM/AI failures surfaced to the UI.

Non-chat LLM features (Interpretation AI drafts, glossary enrichment, semantic
resolve, mapping, CRR/DPM) each hit their own endpoint. This module gives them a
single scrubbed, friendly error payload — ``{summary, detail, status}`` — so the
frontend can render one shared "AI action failed" banner instead of leaking raw
500s or failing silently. The chat feature keeps its own first-person wording
(``api/routes/chat.py``) but shares ``scrub_secrets`` from here.
"""
from __future__ import annotations

import os

#: Provider key env-vars whose values must never leak into an error detail.
_KEY_ENVS = ("AZURE_FOUNDRY_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")


def scrub_secrets(text: str, api_key_env: str | None = None) -> str:
    """Redact any configured API-key value that leaked into an error string."""
    envs = set(_KEY_ENVS)
    if api_key_env:
        envs.add(api_key_env)
    for env_name in envs:
        val = os.environ.get(env_name)
        if val and len(val) > 6 and val in text:
            text = text.replace(val, "***redacted***")
    return text[:800]


def format_llm_error(exc: Exception, api_key_env: str | None = None) -> dict:
    """Turn a backend/LLM failure into a provider-agnostic, user-facing payload.

    Shape: ``{"summary": str, "detail": str, "status": int | None}`` — ``summary``
    is a friendly one-liner, ``detail`` is the scrubbed raw error for the banner's
    collapsible "Technical details".
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    name = type(exc).__name__
    if status in (401, 403):
        summary = ("Couldn't reach the AI service — access was denied. The API key may be wrong "
                   "or the AI resource's network/firewall rules block this machine.")
    elif status == 404:
        summary = "Couldn't reach the AI service — the configured model deployment wasn't found."
    elif status == 429:
        summary = "The AI service is busy right now (rate limit). Please try again in a moment."
    elif isinstance(status, int) and status >= 500:
        summary = "The AI service reported an internal error. Please try again shortly."
    elif "Connection" in name or "Timeout" in name:
        summary = "Couldn't reach the AI service — the connection failed or timed out."
    elif isinstance(exc, ValueError):
        summary = "The AI service isn't configured. Set the API key and endpoint in the .env file."
    else:
        summary = "Something went wrong while contacting the AI service."
    return {"summary": summary, "detail": scrub_secrets(str(exc), api_key_env), "status": status}
