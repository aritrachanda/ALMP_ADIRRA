"""GET /health and GET /readiness — liveness and readiness checks."""
from __future__ import annotations

import os
from uuid import uuid4

from fastapi import APIRouter, Depends

from api.deps import get_project

router = APIRouter(tags=["health"])

# Unique per process — regenerated on every server (re)start, so clients can detect a
# restart by watching for a changed value.
_BOOT_ID = uuid4().hex


@router.get("/health")
async def health():
    return {"status": "ok", "boot_id": _BOOT_ID}


@router.get("/readiness")
async def readiness(project: dict = Depends(get_project)):
    return {
        "status": "ok",
        "project": project.get("name", "unknown"),
        "provider": project.get("agent", {}).get("provider", "not configured"),
    }


def _classify_ai_error(exc: Exception, model: str, kind: str) -> str:
    msg = str(exc)
    if "404" in msg:
        if kind == "embedding":
            return (
                f"Embedding deployment '{model}' was not found for this endpoint. "
                "Vector search is unavailable; CRR/DPM now use a keyword fallback with lower precision "
                "until this deployment is available."
            )
        return (
            f"Generation deployment '{model}' was not found for this endpoint. "
            "Direct AI generation calls will fail until this deployment is available."
        )
    if "401" in msg or "403" in msg:
        return "Authentication/authorization failed for the configured endpoint or key."
    if "429" in msg:
        return "Rate limit reached. Retry after cooldown."
    return f"{kind.capitalize()} check failed: {msg}"


@router.get("/readiness/ai")
async def readiness_ai(project: dict = Depends(get_project)):
    """Check AI readiness for both text generation and embeddings.

    This endpoint is designed to quickly diagnose the common split-brain issue where
    generation works but RAG embedding calls fail.
    """
    agent_cfg = project.get("agent", {})
    provider = str(agent_cfg.get("provider", "not configured")).lower()

    generation_model = str(agent_cfg.get("model", "gpt-5.4-mini"))
    embedding_model = str(agent_cfg.get("embedding_model", "text-embedding-3-large"))
    endpoint = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
    api_key_env = str(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"))
    has_key = bool(os.environ.get(api_key_env, ""))

    if provider != "azure":
        return {
            "status": "skipped",
            "provider": provider,
            "message": "AI readiness checks currently run only for provider=azure.",
            "checks": {},
        }

    from foundry_client import create_foundry_client

    checks = {
        "generation": {
            "model": generation_model,
            "status": "unknown",
            "message": "",
        },
        "embedding": {
            "model": embedding_model,
            "status": "unknown",
            "message": "",
        },
    }

    try:
        client = create_foundry_client(api_key_env=api_key_env)
    except Exception as exc:
        return {
            "status": "error",
            "provider": provider,
            "endpoint_configured": bool(endpoint),
            "api_key_configured": has_key,
            "message": f"Unable to create AI client: {exc}",
            "checks": checks,
        }

    try:
        resp = client.responses.create(model=generation_model, input="Reply with exactly OK")
        checks["generation"]["status"] = "ok"
        checks["generation"]["message"] = f"Generation model reachable. Sample response: {resp.output_text}".strip()
    except Exception as exc:
        checks["generation"]["status"] = "error"
        checks["generation"]["message"] = _classify_ai_error(exc, generation_model, "generation")

    try:
        emb = client.embeddings.create(model=embedding_model, input="healthcheck")
        dim = len(emb.data[0].embedding) if emb.data else 0
        checks["embedding"]["status"] = "ok"
        checks["embedding"]["message"] = f"Embedding model reachable. Vector dimension: {dim}."
    except Exception as exc:
        checks["embedding"]["status"] = "error"
        checks["embedding"]["message"] = _classify_ai_error(exc, embedding_model, "embedding")

    statuses = {checks["generation"]["status"], checks["embedding"]["status"]}
    overall = "ok" if statuses == {"ok"} else "degraded"
    if statuses == {"error"}:
        overall = "error"

    summary = (
        "Both generation and embedding checks passed."
        if overall == "ok"
        else "One or more AI checks failed. Review per-check messages for exact cause."
    )

    return {
        "status": overall,
        "provider": provider,
        "endpoint_configured": bool(endpoint),
        "api_key_configured": has_key,
        "summary": summary,
        "checks": checks,
    }
